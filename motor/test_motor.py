"""
Motor birim testleri (ağa çıkmaz). Çalıştırma:
  cd motor && python -m unittest test_motor -v
"""
import json
import os
import unittest
from unittest import mock

import llm

KISA_SEMA = {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {
    "pmid": {"type": "STRING"}}, "required": ["pmid"]}}


class Yanit:
    def __init__(self, durum, govde, basliklar=None):
        self.status_code, self.ok = durum, 200 <= durum < 300
        self._govde = govde
        self.text = govde if isinstance(govde, str) else json.dumps(govde)
        self.headers = basliklar or {}

    def json(self):
        return self._govde if not isinstance(self._govde, str) else json.loads(self._govde)


def gemini_ok(veri):
    return Yanit(200, {"candidates": [{"content": {"parts": [{"text": json.dumps(veri)}]}}]})


def openai_ok(metin):
    return Yanit(200, {"choices": [{"message": {"content": metin}}]})


def zincir(*tanimlar, **kw):
    ortam = {"GEMINI_API_KEY": "g", "GROQ_API_KEY": "q", "GITHUB_TOKEN": "h",
             "OLLAMA_URL": "http://localhost:11434"}
    with mock.patch.dict(os.environ, ortam, clear=True):
        return llm.Zincir([llm.saglayici_kur(t) for t in tanimlar], **kw)


class ZincirTesti(unittest.TestCase):
    def setUp(self):
        self.uyku = mock.patch("llm.time.sleep").start()
        self.addCleanup(mock.patch.stopall)

    def calistir(self, z, yanitlar, metin="soru", sema=KISA_SEMA):
        giden = []

        def post(url, json=None, **kw):
            giden.append((url, json))
            return yanitlar.pop(0)
        with mock.patch("llm.requests.post", side_effect=post):
            return z.uret(metin, sema=sema), giden

    def test_ilk_saglayici_yanit_verirse_o_kullanilir(self):
        z = zincir("gemini:a", "groq:b")
        veri, giden = self.calistir(z, [gemini_ok([{"pmid": "1"}])])
        self.assertEqual(veri, [{"pmid": "1"}])
        self.assertEqual(len(giden), 1)
        self.assertEqual(z.son_model, "a")

    def test_yogunsa_baska_saglayiciya_gecer(self):
        z = zincir("gemini:a", "groq:llama", yogun_deneme=2)
        veri, giden = self.calistir(z, [
            Yanit(503, "overloaded"), Yanit(503, "overloaded"),
            openai_ok('```json\n{"sonuc": [{"pmid": "7"}]}\n```')])
        self.assertEqual(veri, [{"pmid": "7"}])  # {"sonuc": [...]} açıldı
        self.assertIn("api.groq.com", giden[2][0])
        self.assertEqual(giden[2][1]["response_format"], {"type": "json_object"})
        self.assertEqual(z.son_model, "groq/llama")
        self.assertEqual(z.kullanim, {"groq/llama": 1})
        self.assertIn("a: yoğun", z.notlar)

    def test_gunluk_kota_dolan_bir_daha_denenmez(self):
        z = zincir("gemini:a", "gemini:b")
        self.calistir(z, [Yanit(429, "Quota exceeded ... PerDay"), gemini_ok([{"pmid": "1"}])])
        _, giden = self.calistir(z, [gemini_ok([{"pmid": "2"}])])
        self.assertIn("/b:generateContent", giden[0][0])

    def test_dakika_kotasinda_bekleyip_ayni_saglayiciyi_dener(self):
        z = zincir("gemini:a", "gemini:b")
        _, giden = self.calistir(z, [Yanit(429, "rate", {"retry-after": "5"}),
                                     gemini_ok([{"pmid": "1"}])])
        self.assertTrue(all("/a:" in u for u, _ in giden))
        self.uyku.assert_called_with(6)

    def test_semaya_uymayan_yanit_reddedilir(self):
        z = zincir("gemini:a", "gemini:b")
        veri, _ = self.calistir(z, [gemini_ok({"yanlis": 1}), gemini_ok([{"pmid": "3"}])])
        self.assertEqual(veri, [{"pmid": "3"}])
        self.assertEqual(z.son_model, "b")

    def test_uzun_metin_kucuk_sinirli_saglayiciya_gitmez(self):
        z = zincir("github:openai/gpt-4.1-mini", "gemini:a")
        _, giden = self.calistir(z, [gemini_ok([{"pmid": "1"}])], metin="x" * 30000)
        self.assertIn("generativelanguage", giden[0][0])

    def test_json_modu_desteklenmezse_talimatla_dener(self):
        z = zincir("groq:b")
        veri, giden = self.calistir(z, [
            Yanit(400, "response_format is not supported"),
            openai_ok('Elbette: {"sonuc": [{"pmid": "4"}]}')])
        self.assertEqual(veri, [{"pmid": "4"}])
        self.assertNotIn("response_format", giden[1][1])
        self.assertEqual(giden[1][1]["messages"][0]["content"].count("Yanıtı YALNIZCA"), 1)

    def test_ollama_semayi_format_olarak_alir(self):
        z = zincir("ollama:gemma3:4b")
        veri, giden = self.calistir(z, [Yanit(200, {"message": {"content": '[{"pmid": "5"}]'}})])
        self.assertEqual(veri, [{"pmid": "5"}])
        self.assertEqual(giden[0][1]["model"], "gemma3:4b")
        self.assertEqual(giden[0][1]["format"]["type"], "array")
        self.assertEqual(giden[0][1]["format"]["items"]["type"], "object")

    def test_hepsi_basarisizsa_hata(self):
        z = zincir("gemini:a", yogun_deneme=1)
        with self.assertRaises(RuntimeError):
            self.calistir(z, [Yanit(503, "x")])

    def test_anahtarsiz_saglayici_zincire_girmez(self):
        with mock.patch.dict(os.environ, {"GEMINI_API_KEY": "g"}, clear=True):
            z = llm.Zincir()
        self.assertTrue(all(isinstance(s, llm.GeminiSaglayici) for s in z.saglayicilar))
        self.assertEqual(z.model, "gemini-flash-latest")

    def test_zincir_degiskenle_degistirilebilir(self):
        ortam = {"GEMINI_API_KEY": "g", "OLLAMA_URL": "http://x",
                 "LLM_ZINCIRI": "ollama:qwen3:8b, gemini:z"}
        with mock.patch.dict(os.environ, ortam, clear=True):
            z = llm.Zincir()
        self.assertEqual([s.ad for s in z.saglayicilar], ["ollama/qwen3:8b", "z"])


if __name__ == "__main__":
    unittest.main()
