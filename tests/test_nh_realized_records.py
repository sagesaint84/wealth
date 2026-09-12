import unittest
from app.services.nh_realized import *

class NhRecordTests(unittest.TestCase):
    def row(self): return {"date":"2026-01-02","code":"SYN","quantity":1.0,"buy_amount":10.0,"sell_amount":20.0,"pnl":10.0,"currency":"KRW"}
    def test_new_replay_manual_and_multiset(self):
        row=self.row(); result=classify_nh_rows([row,row],[],"opaque-a")
        self.assertEqual([x["status"] for x in result],[NEW,NEW]); self.assertNotEqual(result[0]["fingerprint"],result[1]["fingerprint"])
        imported={"source":"nh","source_fingerprint":result[0]["fingerprint"]}
        self.assertEqual(classify_nh_rows([row],[imported],"opaque-a")[0]["status"],ALREADY_IMPORTED)
        self.assertEqual(classify_nh_rows([row],[{"source":"manual","date":row["date"],"code":row["code"],"pnl":row["pnl"]}],"opaque-a")[0]["status"],POSSIBLE_DUPLICATE)
        self.assertEqual(classify_nh_rows([row],[imported],"opaque-b")[0]["status"],NEW)
    def test_invalid_required_value(self):
        row=self.row(); row["buy_amount"]=None
        self.assertEqual(classify_nh_rows([row],[],"opaque")[0]["status"],INVALID)
    def test_duplicate_selection_is_invalid_but_distinct_occurrences_survive(self):
        first=dict(self.row(),source_occurrence=0)
        duplicate=classify_nh_rows([first,dict(first)],[],"opaque")
        self.assertEqual([item["status"] for item in duplicate],[NEW,INVALID])
        self.assertEqual(duplicate[1]["reason"],"DUPLICATE_SELECTION")
        distinct=classify_nh_rows([first,dict(self.row(),source_occurrence=1)],[],"opaque")
        self.assertEqual([item["status"] for item in distinct],[NEW,NEW])
        self.assertNotEqual(distinct[0]["fingerprint"],distinct[1]["fingerprint"])
    def test_nonfinite_financial_value_is_invalid(self):
        row=self.row(); row["pnl"]="NaN"
        result=classify_nh_rows([row],[],"opaque")
        self.assertEqual((result[0]["status"],result[0]["reason"]),(INVALID,"NUMERIC_PARSE_ERROR"))
