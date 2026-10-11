"""Real Chrome uses the existing safe harness and synthetic planning endpoint."""
import base64
import json

import pytest

from tests.test_account_reorder_runtime import chrome_preview, wait_for
from tests.test_asset_bucket_chrome import prepare, reload_page, assignment
from tests.test_workflow_ux_chrome import FRAMES, click, no_overflow


def open_picker(call, evaluate):
    if not evaluate("document.querySelector('#wealthBucketEditor').open"):
        click(call, evaluate, '#wealthBucketEditor > summary')
    click(call, evaluate, '.wealth-bucket-edit-row[data-id=core] .wealth-color-trigger')


def input_hex(evaluate, value):
    evaluate(f"(()=>{{const i=document.querySelector('.wealth-bucket-edit-row[data-id=core] .wealth-color-hex');i.focus();i.value={json.dumps(value)};i.dispatchEvent(new Event('input',{{bubbles:true}}))}})()")


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
    assert evaluate('document.activeElement.dataset.color') == '#FB7185'
    call('Input.dispatchKeyEvent', {'type':'keyDown','key':'Escape','code':'Escape','windowsVirtualKeyCode':27})
    assert evaluate('document.activeElement.classList.contains("wealth-color-trigger")')
    open_picker(call, evaluate)
    click(call, evaluate, panel + ' [data-color="#5FC5D9"]')
    click(call, evaluate, '#wealthBucketForm button[type=submit]')
    wait_for(evaluate, "__qState.buckets[0].color==='#5FC5D9'")
    reload_page(call, evaluate)
    evaluate(f"document.documentElement.dataset.theme='{theme}'")
    open_picker(call, evaluate)
    no_overflow(evaluate, 390)
    assert evaluate(f"(()=>{{const r=document.querySelector('{panel}').getBoundingClientRect();return r.left>=0&&r.right<=innerWidth&&r.top>=0&&r.bottom<=innerHeight}})()")
    tmp_path.joinpath(f'color-mobile-{theme}.png').write_bytes(base64.b64decode(call('Page.captureScreenshot', {'format':'png'})['data']))
    call('Emulation.setDeviceMetricsOverride', {'width':1280,'height':900,'deviceScaleFactor':1,'mobile':False})
    evaluate(FRAMES)
    assert evaluate(f"document.querySelector('{panel}').hidden")
    open_picker(call, evaluate)
    assert evaluate(f"document.querySelector('{panel}').dataset.mode") == 'advanced'
