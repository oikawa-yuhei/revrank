"""コミュニティテキストからブランド・型番を抽出するモジュール。

ichiba/normalize.py のブランド辞書・モデルパターンを流用し、
自由テキストから (product_id, brand_key, raw_mention) のリストを返す。
"""
import re
from ichiba.normalize import _BRAND_RE, _MODEL_RULES, _clean, _slug
from community.books_extract import extract_book_mentions


def extract_mentions(text: str) -> list[dict]:
    """
    テキストから商品言及を抽出する。

    Returns:
        [{"product_id": str, "brand_key": str, "brand_display": str,
          "model_name": str, "raw_mention": str}, ...]
    """
    if not text:
        return []

    results = []
    seen_product_ids: set[str] = set()

    # 文単位で分割して処理（1文に複数モデルが出ることもある）
    sentences = re.split(r'[。\n！？!?\.\r]', text)

    for sent in sentences:
        sent = sent.strip()
        if not sent:
            continue
        clean = _clean(sent)

        for brand_key, brand_display, brand_pat in _BRAND_RE:
            if not brand_pat.search(sent):   # 元のテキストでブランド検出
                continue

            rules = _MODEL_RULES.get(brand_key, [])
            for pat, name_fn in rules:
                m = pat.search(clean)
                if not m:
                    continue
                try:
                    model_name = name_fn(m)
                except Exception:
                    continue

                product_id = f"{brand_key}/{_slug(model_name)}"
                if product_id in seen_product_ids:
                    continue

                seen_product_ids.add(product_id)
                # 前後20文字をコンテキストとして保存
                start = max(0, m.start() - 20)
                end   = min(len(clean), m.end() + 20)
                results.append({
                    "product_id":    product_id,
                    "brand_key":     brand_key,
                    "brand_display": brand_display,
                    "model_name":    model_name,
                    "raw_mention":   clean[start:end].strip(),
                })
                break   # 同ブランド内で最初にマッチしたモデルのみ

    # 書籍言及を追記（product_id の重複チェックは books_extract 内で完結）
    for b in extract_book_mentions(text):
        if b["product_id"] not in seen_product_ids:
            seen_product_ids.add(b["product_id"])
            results.append(b)

    return results
