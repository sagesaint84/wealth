"""Offline decoding primitives; no financial storage, credentials or network."""
import os
import re
import subprocess
import threading

MAX_BYTES = 10 * 1024 * 1024
MAX_PAGES = 8
MAX_PIXELS = 16_000_000
# Shared by pension and ledger preview within ONE application process.
DECODE_SLOTS = threading.BoundedSemaphore(2)


def command(args, timeout=12):
    return subprocess.run(args, check=True, stdout=subprocess.PIPE,
                          stderr=subprocess.DEVNULL, timeout=timeout,
                          env={**os.environ, 'OMP_THREAD_LIMIT': '1'}).stdout


def detect_file(data, mime):
    if not data or len(data) > MAX_BYTES:
        raise ValueError('파일은 10MiB 이하로 선택해 주세요.')
    kind = ('pdf' if data.startswith(b'%PDF-') else 'png' if data.startswith(b'\x89PNG\r\n\x1a\n')
            else 'jpeg' if data.startswith(b'\xff\xd8\xff') else None)
    allowed = {'pdf': 'application/pdf', 'png': 'image/png', 'jpeg': 'image/jpeg'}
    if kind is None or mime not in (allowed[kind], 'application/octet-stream'):
        raise ValueError('PDF, PNG, JPG 파일 형식을 확인해 주세요.')
    return kind


def extract_pages(path, kind, *, run=command, needs_ocr, tsv=False, refine_tsv=None):
    """Decode to bounded transient text pages; caller chooses its own text policy.

    command injection preserves the pension worker's existing mock contract.
    Raw text never goes to logs; the domain parser must allowlist its response.
    """
    from PIL import Image, ImageOps
    Image.MAX_IMAGE_PIXELS = MAX_PIXELS
    directory = path.parent

    def ocr(image_path):
        with Image.open(image_path) as image:
            if (image.format not in {'PNG', 'JPEG'} or image.width * image.height > MAX_PIXELS
                    or getattr(image, 'n_frames', 1) != 1):
                raise ValueError('Image limit')
            image = ImageOps.exif_transpose(image).convert('L')
            image.thumbnail((3200, 3200))
            image = ImageOps.autocontrast(image)
            prepared = directory / 'prepared.png'
            image.save(prepared); os.chmod(prepared, 0o600)
        try:
            orientation = run(['tesseract', str(prepared), 'stdout', '-l', 'osd', '--psm', '0'], 5).decode('utf-8')
            rotation = re.search(r'Rotate:\s*(90|180|270)', orientation)
            if rotation:
                with Image.open(prepared) as image:
                    image.rotate(-int(rotation[1]), expand=True).save(directory / 'rotated.png')
                prepared = directory / 'rotated.png'; os.chmod(prepared, 0o600)
        except subprocess.CalledProcessError:
            pass
        args = ['tesseract', str(prepared), 'stdout', '-l', 'kor+eng', '--psm', '6']
        if tsv:
            args.append('tsv')
        output = run(args, 20)
        if len(output) > 200_000:
            raise ValueError('Text limit')
        text = output.decode('utf-8')
        # Opt-in only. Run while this exact oriented/scaled page still exists;
        # no later page can overwrite the pixels referenced by its TSV boxes.
        lines = refine_tsv(text, prepared, run) if tsv and refine_tsv else None
        return text, lines

    if kind != 'pdf':
        text, lines = ocr(path)
        page = {'page': 1, 'text': text, 'method': 'ocr_tsv' if tsv else 'ocr'}
        if lines is not None:
            page['ocr_lines'] = lines
        return [page]
    info = run(['pdfinfo', str(path)]).decode('utf-8', errors='replace')
    pages = re.search(r'^Pages:\s*(\d+)', info, re.M)
    if not pages or not 1 <= int(pages[1]) <= MAX_PAGES or re.search(r'^Encrypted:\s*yes', info, re.M):
        raise ValueError('PDF limit')
    result = []
    total_text = 0
    for page in range(1, int(pages[1]) + 1):
        output = directory / 'page.txt'
        run(['pdftotext', '-f', str(page), '-l', str(page), '-layout', '-enc', 'UTF-8', str(path), str(output)])
        os.chmod(output, 0o600)
        if output.stat().st_size > 200_000:
            raise ValueError('Text limit')
        text = output.read_text(encoding='utf-8')
        method = 'text'
        lines = None
        if needs_ocr(text):
            prefix = directory / 'page'
            run(['pdftoppm', '-f', str(page), '-l', str(page), '-singlefile', '-scale-to', '3200', '-png', str(path), str(prefix)])
            image = directory / 'page.png'; os.chmod(image, 0o600)
            text, lines = ocr(image); method = 'ocr_tsv' if tsv else 'ocr'
        total_text += len(text)
        if total_text > 200_000:
            raise ValueError('Text limit')
        item = {'page': page, 'text': text, 'method': method}
        if lines is not None:
            item['ocr_lines'] = lines
        result.append(item)
    return result


def set_worker_limits():
    if os.name == 'posix':
        import resource
        resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024,) * 2)
        resource.setrlimit(resource.RLIMIT_CPU, (60, 60))
        resource.setrlimit(resource.RLIMIT_FSIZE, (20 * 1024 * 1024,) * 2)
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    os.umask(0o077)
