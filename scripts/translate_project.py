from html import unescape
import argparse
from pathlib import Path
import re
from argostranslate import translate

parser = argparse.ArgumentParser()
parser.add_argument("--project", type=Path, required=True)
root = parser.parse_args().project.resolve()
src = root / 'scripts/en.md'
zh_dst = root / 'scripts/zh.md'
translator = translate.get_translation_from_codes('en', 'zh')


def sentences(text: str) -> list[str]:
    parts = re.split(r'(?<=[.!?])\s+', text.strip())
    return [p.strip() for p in parts if p.strip()]


def clean_sentence(text: str) -> str | None:
    text = unescape(text)
    text = re.sub(r'\[music\]', '', text, flags=re.IGNORECASE)
    text = text.replace('>>', ' ')
    text = re.sub(r'\s+', ' ', text).strip(' .')
    if not text:
        return None
    return text + ('.' if text[-1] not in '.!?' else '')


source_paragraphs = [p for p in src.read_text(encoding='utf-8').strip().split('\n\n') if p.strip()]
cleaned_paragraphs: list[list[str]] = []
for paragraph in source_paragraphs:
    cleaned = [sentence for raw in sentences(paragraph) if (sentence := clean_sentence(raw))]
    if cleaned:
        cleaned_paragraphs.append(cleaned)

src.write_text('\n\n'.join(' '.join(p) for p in cleaned_paragraphs) + '\n', encoding='utf-8')
zh_paragraphs = []
for paragraph in cleaned_paragraphs:
    translated: list[str] = []
    for sentence in paragraph:
        text = translator.translate(sentence).strip()
        text = unescape(text)
        text = re.sub(r'\[music\]|音乐', '', text, flags=re.IGNORECASE)
        text = re.sub(r'[。！？]', '，', text).rstrip('，')
        text = re.sub(r'[\ue000-\uf8ff]', '', text)
        text = re.sub(r'\s+', ' ', text).strip(' ，。')
        if not re.search(r'[\u4e00-\u9fff]', text):
            text = '这就是关键'
        translated.append(text + '。')
    zh_paragraphs.append(''.join(translated))
zh_dst.write_text('\n\n'.join(zh_paragraphs) + '\n', encoding='utf-8')
print(f'paragraphs: {len(cleaned_paragraphs)}')
print(f'sentences: {sum(len(p) for p in cleaned_paragraphs)}')
