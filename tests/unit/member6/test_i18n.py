from nexa.i18n.service import TranslationService


def test_english_and_arabic_catalogs_share_keys():
    en = TranslationService("en")
    ar = TranslationService("ar")
    assert set(en._catalogs["en"]) == set(ar._catalogs["ar"])


def test_arabic_is_rtl_and_english_is_ltr():
    trans = TranslationService("en")
    assert trans.t("nav.dashboard") == "Dashboard"
    assert not trans.is_rtl()
    trans.set_language("ar")
    assert trans.is_rtl()
    assert trans.t("nav.dashboard") == "لوحة التحكم"


def test_missing_key_falls_back_to_english_then_key():
    trans = TranslationService("ar")
    assert trans.t("this.key.does.not.exist") == "this.key.does.not.exist"
