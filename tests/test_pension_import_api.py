"""Synthetic owner scope and bounded raw-body upload, without running decoders."""
import asyncio
from unittest.mock import Mock

import pytest
from fastapi import HTTPException

from tests.test_national_pension_history import users
from regression_support import import_main_without_loading_real_env
from app.services import national_pension_import as imp


class Request:
    def __init__(self,data=b'%PDF-synthetic',body=None):
        self.headers={'content-type':'application/pdf'};self.data=data;self.body=body;self.consumed=False
    async def stream(self):
        self.consumed=True
        yield self.data
    async def json(self):return self.body


def test_preview_uses_authenticated_owner_before_upload_and_bounded_stream(users,monkeypatch):
    main=import_main_without_loading_real_env()
    monkeypatch.setattr(main,'get_current_username',lambda request:'alice')
    decode=Mock(return_value={'fields':[]});monkeypatch.setattr(imp,'preview',decode)
    request=Request()
    assert asyncio.run(main.preview_national_pension_document('alice-np',request,'auto'))=={'fields':[]}
    decode.assert_called_once_with('alice-np','alice',b'%PDF-synthetic','application/pdf','auto')
    foreign=Request()
    with pytest.raises(HTTPException) as denied:asyncio.run(main.preview_national_pension_document('bob-np',foreign,'auto'))
    assert denied.value.status_code==404 and not foreign.consumed
    with pytest.raises(HTTPException) as large:asyncio.run(main.preview_national_pension_document('alice-np',Request(b'x'*(imp.MAX_BYTES+1)),'auto'))
    assert large.value.status_code==413 and decode.call_count==1


def test_apply_conflict_keeps_original_portfolio_and_returns_safe_status(users,monkeypatch):
    from tests.test_national_pension_import import item, request_payload
    main=import_main_without_loading_real_env();monkeypatch.setattr(main,'get_current_username',lambda request:'alice')
    payload=request_payload(item(),unpaid_amount=100)
    payload['expected']['total_paid_amount']=0
    before=(users/'alice/portfolio.json').read_bytes()
    with pytest.raises(HTTPException) as error:asyncio.run(main.apply_national_pension_document('alice-np',Request(body=payload)))
    assert error.value.status_code==409
    assert (users/'alice/portfolio.json').read_bytes()==before
