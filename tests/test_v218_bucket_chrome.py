"""Direct target editing reuses canonical planning writes; synthetic portfolio only."""
import pytest
from tests.test_account_reorder_runtime import chrome_preview, wait_for
from tests.test_asset_bucket_chrome import prepare

@pytest.mark.parametrize('width',[320,360,390,768,1280])
@pytest.mark.parametrize('theme',['purple','white','oled'])
def test_target_edit_validation_save_and_readonly_current(chrome_preview,width,theme):
    call,evaluate=prepare(chrome_preview,width)
    evaluate(f"setAppTheme({theme!r})")
    baseline=evaluate('JSON.stringify({view:__qView,accounts:__qState.accounts,holdings:__qState.holdings})')
    evaluate('document.querySelector("[data-bucket-target=core]").click()')
    assert evaluate('document.getElementById("wealthBucketTargetDialog").open')
    assert evaluate('__qState.buckets[0].target')==40
    evaluate('document.querySelector("#wealthBucketTargetDialog input").value="90";document.querySelector("#wealthBucketTargetDialog form").requestSubmit()')
    assert '100%' in evaluate('document.querySelector("#wealthBucketTargetDialog [role=status]").textContent')
    assert not evaluate('__qRequests.some(r=>r.path.endsWith("/buckets"))')
    evaluate('document.querySelector("#wealthBucketTargetDialog input").value="30";document.querySelector("#wealthBucketTargetDialog form").requestSubmit()')
    wait_for(evaluate,'!document.getElementById("wealthBucketTargetDialog").open')
    assert evaluate('__qState.buckets.map(b=>b.target)')==[30,40,20]
    assert evaluate('document.querySelector(".wealth-bucket-edit-row[data-id=core] [name=target]").value')=='30'
    assert baseline==evaluate('JSON.stringify({view:__qView,accounts:__qState.accounts,holdings:__qState.holdings})')
    evaluate('document.querySelector(".wealth-bucket-donut[data-bucket-chart=current]").click()')
    assert not evaluate('document.getElementById("wealthBucketTargetDialog").open')
    evaluate('(()=>{const n=document.querySelector(".wealth-bucket-donut[data-bucket-chart=target]"),r=n.getBoundingClientRect();n.dispatchEvent(new MouseEvent("click",{clientX:r.x+r.width/2,clientY:r.y+r.height/2}));})()')
    assert not evaluate('document.getElementById("wealthBucketTargetDialog").open')
    evaluate('(()=>{const n=document.querySelector(".wealth-bucket-donut[data-bucket-chart=target]"),r=n.getBoundingClientRect();n.dispatchEvent(new MouseEvent("click",{clientX:r.x+r.width*.78,clientY:r.y+r.height/2}));})()')
    assert not evaluate('document.getElementById("wealthBucketTargetDialog").open')
    evaluate('(()=>{const n=document.querySelector(".wealth-bucket-donut[data-bucket-chart=target]"),r=n.getBoundingClientRect();n.dispatchEvent(new MouseEvent("click",{clientX:r.x+r.width*.85,clientY:r.y+r.height/2}));})()')
    assert evaluate('document.getElementById("wealthBucketTargetDialog").open')
    call('Input.dispatchKeyEvent',{'type':'keyDown','key':'Escape','windowsVirtualKeyCode':27})
    call('Input.dispatchKeyEvent',{'type':'keyUp','key':'Escape','windowsVirtualKeyCode':27})
    wait_for(evaluate,'!document.getElementById("wealthBucketTargetDialog").open')
    evaluate('document.querySelector("[data-bucket-target=core]").focus()')
    call('Input.dispatchKeyEvent',{'type':'rawKeyDown','key':'Enter','code':'Enter','windowsVirtualKeyCode':13})
    down=evaluate('({open:document.getElementById("wealthBucketTargetDialog").open,active:document.activeElement.outerHTML,writes:__qRequests})')
    call('Input.dispatchKeyEvent',{'type':'keyUp','key':'Enter','code':'Enter','windowsVirtualKeyCode':13})
    assert evaluate('document.getElementById("wealthBucketTargetDialog").open'), down
    evaluate('document.getElementById("wealthBucketTargetDialog").close()')
    assert evaluate('document.documentElement.scrollWidth<=innerWidth+1')

def test_target_conflict_preserves_input_and_unsaved_editor(chrome_preview):
    _,evaluate=prepare(chrome_preview,360)
    evaluate('document.querySelector("[data-bucket-target=core]").click();__qState.revision++;document.querySelector("#wealthBucketTargetDialog input").value="30";document.querySelector("#wealthBucketTargetDialog form").requestSubmit()')
    wait_for(evaluate,'document.querySelector("#wealthBucketTargetDialog [role=status]").textContent.includes("입력값은 보존")')
    assert evaluate('document.querySelector("#wealthBucketTargetDialog input").value')=='30'
    assert evaluate('__qState.buckets[0].target')==40
    evaluate('document.getElementById("wealthBucketTargetDialog").close();document.querySelector(".wealth-bucket-edit-row[data-id=core] [name=target]").dispatchEvent(new Event("input",{bubbles:true}));document.querySelector("[data-bucket-target=core]").click()')
    assert not evaluate('document.getElementById("wealthBucketTargetDialog").open')
