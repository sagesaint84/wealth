"""Real Chrome uses the existing safe harness and synthetic planning endpoint."""
import base64
import json

import pytest

from tests.test_account_reorder_runtime import chrome_preview, wait_for
from tests.test_asset_bucket_chrome import prepare, reload_page, assignment
from tests.test_workflow_ux_chrome import FRAMES, click, no_overflow


PALETTE = ['#FF5A5F', '#FF9F1C', '#FFD60A', '#2ECF73', '#22C7B8', '#4D96FF', '#7C6CFF', '#FF5FA2']


def open_picker(call, evaluate):
    if not evaluate("document.querySelector('#wealthBucketEditor').open"):
        click(call, evaluate, '#wealthBucketEditor > summary')
    click(call, evaluate, '.wealth-bucket-edit-row[data-id=core] .wealth-color-trigger')
    swatches = evaluate("""[...document.querySelectorAll('.wealth-bucket-edit-row[data-id=core] .wealth-color-choices button')].map(b=>{
      const r=b.getBoundingClientRect();return {color:b.dataset.color,x:r.x,y:r.y,width:r.width,height:r.height};})""")
    assert [s['color'] for s in swatches] == PALETTE
    assert len({s['x'] for s in swatches}) == 4
    assert len({s['y'] for s in swatches}) == 2
    assert all(s['width'] >= 40 and s['height'] == 36 for s in swatches)
    assert evaluate("getComputedStyle(document.querySelector('.wealth-bucket-edit-row[data-id=core] .wealth-color-current')).display") != 'none'


def input_hex(evaluate, value):
    evaluate(f"(()=>{{const i=document.querySelector('.wealth-bucket-edit-row[data-id=core] .wealth-color-hex');i.focus();i.value={json.dumps(value)};i.dispatchEvent(new Event('input',{{bubbles:true}}))}})()")


@pytest.mark.parametrize('theme', ['purple', 'white', 'oled'])
def test_hue_spectrum_native_pointer_and_keyboard(chrome_preview, theme, tmp_path):
    call, evaluate = prepare(chrome_preview, 1280)
    evaluate(f"document.documentElement.dataset.theme='{theme}'")
    open_picker(call, evaluate)
    panel = '.wealth-bucket-edit-row[data-id=core] .wealth-color-palette'
    hue = panel + ' .wealth-color-hue'
    hex_input = panel + ' .wealth-color-hex'
    assert 'linear-gradient(to right' in evaluate(f"getComputedStyle(document.querySelector('{hue}')).getPropertyValue('--hue-spectrum')")
    assert evaluate(f"document.querySelector('{hue}').getAttribute('aria-label')") == '색상(Hue)'
    click(call, evaluate, hue)
    middle = int(evaluate(f"document.querySelector('{hue}').value"))
    assert 179 <= middle <= 180
    # Native range movement must keep the draft and SV hue synchronized, without saving.
    for key, code, expected in [('Home', 36, 0), ('End', 35, 359), ('ArrowLeft', 37, 358), ('Home', 36, 0)]:
        expected_hex = evaluate(f"(()=>{{const sv=WealthColorPicker.hexToHsv(document.querySelector('{hex_input}').value);return WealthColorPicker.hsvToHex({expected},sv.s,sv.v)}})()")
        call('Input.dispatchKeyEvent', {'type': 'keyDown', 'key': key, 'code': key, 'windowsVirtualKeyCode': code})
        call('Input.dispatchKeyEvent', {'type': 'keyUp', 'key': key, 'code': key, 'windowsVirtualKeyCode': code})
        assert int(evaluate(f"document.querySelector('{hue}').value")) == expected
        assert evaluate(f"document.querySelector('{hex_input}').value") == expected_hex
        assert evaluate(f"getComputedStyle(document.querySelector('{panel} .wealth-color-sv')).getPropertyValue('--hue-color').trim()") == evaluate(f"WealthColorPicker.hsvToHex({expected},1,1)")
    assert evaluate('__qState.buckets[0].color || null') is None
    no_overflow(evaluate, 1280)
    bounds = evaluate(f"(()=>{{const r=document.querySelector('{hue}').getBoundingClientRect();return {{x:r.x,y:r.y,width:r.width,height:r.height}}}})()")
    tmp_path.joinpath(f'hue-spectrum-{theme}.json').write_text(json.dumps(bounds), encoding='utf-8')
    tmp_path.joinpath(f'hue-spectrum-{theme}.png').write_bytes(base64.b64decode(call('Page.captureScreenshot', {'format': 'png'})['data']))


@pytest.mark.parametrize('theme', ['purple', 'white', 'oled'])
def test_desktop_free_color_hex_validation_preview_save_reload(chrome_preview, theme, tmp_path):
    call, evaluate = prepare(chrome_preview, 1280)
    before = evaluate('JSON.stringify(__qView)')
    evaluate(f"document.documentElement.dataset.theme='{theme}'")
    open_picker(call, evaluate)
    panel = '.wealth-bucket-edit-row[data-id=core] .wealth-color-palette'
    assert evaluate(f"document.querySelector('{panel}').dataset.mode") == 'advanced'
    # Native pointer selects an arbitrary point in SV, not a recommended swatch.
    bounds = evaluate(f"(()=>{{const r=document.querySelector('{panel} .wealth-color-sv').getBoundingClientRect();return {{x:r.x+r.width*.63,y:r.y+r.height*.31}}}})()")
    call('Input.dispatchMouseEvent', {'type': 'mousePressed', **bounds, 'button': 'left', 'clickCount': 1})
    call('Input.dispatchMouseEvent', {'type': 'mouseReleased', **bounds, 'button': 'left', 'clickCount': 1})
    pointer_color = evaluate(f"document.querySelector('{panel} .wealth-color-hex').value")
    assert evaluate(f"WealthColorPicker.isValidHexColor({json.dumps(pointer_color)})")
    assert pointer_color != '#A78BFA'
    # Hue range and SV arrow keys both work independently of palette clicks.
    evaluate(f"(()=>{{const h=document.querySelector('{panel} .wealth-color-hue');h.value='210';h.dispatchEvent(new Event('input',{{bubbles:true}}));document.querySelector('{panel} .wealth-color-sv').focus()}})()")
    old = evaluate(f"document.querySelector('{panel} .wealth-color-hex').value")
    call('Input.dispatchKeyEvent', {'type': 'keyDown', 'key': 'ArrowRight', 'code': 'ArrowRight', 'windowsVirtualKeyCode': 39})
    assert evaluate(f"document.querySelector('{panel} .wealth-color-hex').value") != old
    click(call, evaluate, panel + ' .wealth-color-apply')
    free_color = evaluate("document.querySelector('.wealth-bucket-edit-row[data-id=core] .wealth-color-picker').dataset.color")
    assert free_color not in evaluate('WealthColorPicker.getRecommendedPalette()')
    # Unsaved accent previews change, financial values and persisted metadata do not.
    assert evaluate('__qState.buckets[0].color || null') is None
    assert evaluate("getComputedStyle(document.querySelector('[data-bucket-filter=core]')).getPropertyValue('--bucket-color').trim()") == free_color
    click(call, evaluate, '#wealthBucketForm button[type=submit]')
    wait_for(evaluate, f"__qState.buckets[0].color==={json.dumps(free_color)}")
    reload_page(call, evaluate)
    evaluate(f"document.documentElement.dataset.theme='{theme}'")
    evaluate("window.dispatchEvent(new CustomEvent('wealth:portfolio',{detail:__qView}))")
    open_picker(call, evaluate)
    assert evaluate(f"document.querySelector('{panel} .wealth-color-hex').value") == free_color
    request_count = evaluate('__qRequests.length')
    for invalid in ['#XYZXYZ', '#12345678', '#abc', 'red']:
        input_hex(evaluate, invalid)
        assert evaluate(f"document.querySelector('{panel} .wealth-color-apply').disabled")
        assert evaluate(f"document.querySelector('{panel} .wealth-color-hex').getAttribute('aria-invalid')") == 'true'
        call('Input.dispatchKeyEvent', {'type': 'keyDown', 'key': 'Enter', 'code': 'Enter', 'windowsVirtualKeyCode': 13})
        assert evaluate('__qRequests.length') == request_count
        assert evaluate('__qState.buckets[0].color') == free_color
    input_hex(evaluate, '#12abef')
    assert evaluate(f"document.querySelector('{panel} .wealth-color-apply').disabled") is False
    click(call, evaluate, panel + ' .wealth-color-apply')
    click(call, evaluate, '#wealthBucketForm button[type=submit]')
    wait_for(evaluate, "__qState.buckets[0].color==='#12ABEF'")
    assignment(call, evaluate, 'core')
    for selector in ('[data-bucket-filter=core]', '.wealth-bucket-legend-row[data-bucket-key=core]', '[data-assign-holding=h1]'):
        assert evaluate(f"getComputedStyle(document.querySelector({json.dumps(selector)})).getPropertyValue('--bucket-color').trim()") == '#12ABEF'
    assert evaluate('JSON.stringify(__qView)') == before
    open_picker(call, evaluate)
    no_overflow(evaluate, 1280)
    assert evaluate(f"(()=>{{const r=document.querySelector('{panel}').getBoundingClientRect();return r.left>=0&&r.right<=innerWidth&&r.top>=0&&r.bottom<=innerHeight}})()")
    assert evaluate(f"getComputedStyle(document.querySelector('{panel} .wealth-color-hex')).color") == evaluate(f"getComputedStyle(document.querySelector('{panel}')).color")
    tmp_path.joinpath(f'color-desktop-{theme}.png').write_bytes(base64.b64decode(call('Page.captureScreenshot', {'format':'png'})['data']))
    evaluate(f"document.querySelector('{panel} .wealth-color-apply').focus()")
    call('Input.dispatchKeyEvent', {'type':'keyDown','key':'Tab','code':'Tab','windowsVirtualKeyCode':9})
    assert evaluate(f"document.activeElement===document.querySelector('{panel} .wealth-color-choices button')")


@pytest.mark.parametrize('theme', ['purple', 'white', 'oled'])
def test_mobile_palette_focus_escape_and_responsive_mode(chrome_preview, theme, tmp_path):
    call, evaluate = prepare(chrome_preview, 390)
    evaluate(f"document.documentElement.dataset.theme='{theme}'")
    open_picker(call, evaluate)
    panel = '.wealth-bucket-edit-row[data-id=core] .wealth-color-palette'
    assert evaluate(f"document.querySelector('{panel}').dataset.mode") == 'palette'
    assert evaluate(f"getComputedStyle(document.querySelector('{panel} .wealth-color-advanced')).display") == 'none'
    call('Input.dispatchKeyEvent', {'type':'keyDown','key':'ArrowRight','code':'ArrowRight','windowsVirtualKeyCode':39})
    assert evaluate('document.activeElement.dataset.color') == '#FF9F1C'
    call('Input.dispatchKeyEvent', {'type':'keyDown','key':'Escape','code':'Escape','windowsVirtualKeyCode':27})
    assert evaluate('document.activeElement.classList.contains("wealth-color-trigger")')
    open_picker(call, evaluate)
    click(call, evaluate, panel + ' [data-color="#22C7B8"]')
    assert evaluate(f"document.querySelector('{panel} .wealth-color-hex').value") == '#22C7B8'
    assert evaluate(f"document.querySelector('{panel} .wealth-color-current').textContent") == '#22C7B8'
    assert evaluate(f"Number(document.querySelector('{panel} .wealth-color-hue').value)") == evaluate("Math.round(WealthColorPicker.hexToHsv('#22C7B8').h)")
    click(call, evaluate, '#wealthBucketForm button[type=submit]')
    wait_for(evaluate, "__qState.buckets[0].color==='#22C7B8'")
    reload_page(call, evaluate)
    evaluate(f"document.documentElement.dataset.theme='{theme}'")
    open_picker(call, evaluate)
    assert evaluate(f"document.querySelector('{panel} [aria-pressed=true]').dataset.color") == '#22C7B8'
    assert evaluate(f"getComputedStyle(document.querySelector('{panel} [aria-pressed=true]')).outlineWidth") == '2px'
    no_overflow(evaluate, 390)
    assert evaluate(f"(()=>{{const r=document.querySelector('{panel}').getBoundingClientRect();return r.left>=0&&r.right<=innerWidth&&r.top>=0&&r.bottom<=innerHeight}})()")
    tmp_path.joinpath(f'color-mobile-{theme}.png').write_bytes(base64.b64decode(call('Page.captureScreenshot', {'format':'png'})['data']))
    call('Emulation.setDeviceMetricsOverride', {'width':1280,'height':900,'deviceScaleFactor':1,'mobile':False})
    evaluate(FRAMES)
    assert evaluate(f"document.querySelector('{panel}').hidden")
    open_picker(call, evaluate)
    assert evaluate(f"document.querySelector('{panel}').dataset.mode") == 'advanced'
