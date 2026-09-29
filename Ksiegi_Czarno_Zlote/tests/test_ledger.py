import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import json
from app import Ledger, nip_checksum_valid

class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.ledger=Ledger(Path(self.tmp.name)/"test.sqlite3")
    def tearDown(self):
        self.ledger.close();self.tmp.cleanup()
    def test_balanced_entry_posts_and_trial_balance_balances(self):
        eid=self.ledger.add_entry("2026-01-05","OT/1","Wpłata kapitału","",[("130",10000,0,""),("800",0,10000,"")])
        self.assertGreater(eid,0)
        tb=self.ledger.trial_balance()
        self.assertEqual(round(sum(x['debit'] for x in tb),2),10000)
        self.assertEqual(round(sum(x['credit'] for x in tb),2),10000)
    def test_unbalanced_entry_is_rejected(self):
        with self.assertRaisesRegex(ValueError,"niezbilansowany"):
            self.ledger.add_entry("2026-01-05","FV/1","Błędny dekret","",[("130",100,0,""),("800",0,90,"")])
        self.assertEqual(len(self.ledger.entries()),0)
    def test_single_line_cannot_have_debit_and_credit(self):
        with self.assertRaises(ValueError):
            self.ledger.add_entry("2026-01-05","FV/1","Błędny wiersz","",[("130",100,10,""),("800",0,90,"")])
    def test_profit_and_loss_period_is_filtered(self):
        self.ledger.add_entry("2026-01-05","FV/1","Sprzedaż","",[("201",123,0,""),("700",0,100,""),("222",0,23,"")])
        rows=self.ledger.profit_loss("2026-01-01","2026-01-31")
        revenue=next(x for x in rows if x['code']=="700")
        self.assertEqual(revenue['credit'],100)
        self.assertEqual(self.ledger.profit_loss("2026-02-01","2026-02-28"),[])
    def test_nip_checksum(self):
        self.assertTrue(nip_checksum_valid("5260250995"))
        self.assertFalse(nip_checksum_valid("5260250994"))
    def test_vat_api_parsing_with_mock(self):
        payload={"result":{"requestId":"test-id","subject":{"name":"Test Sp. z o.o.","statusVat":"Czynny","regon":"123","krs":"456","accountNumbers":["111"]}}}
        class Response:
            def __enter__(self):return self
            def __exit__(self,*_):pass
            def read(self):return json.dumps(payload).encode()
        with patch("app.urllib.request.urlopen",return_value=Response()):
            data=self.ledger.company_check("Deloitte","5260250995","2026-01-01")
        self.assertEqual(data['statusVat'],"Czynny")
        self.assertEqual(data['name'],"Test Sp. z o.o.")

if __name__ == "__main__":unittest.main()
