import os
import re
import shutil
import fitz  # pymupdf
import pandas as pd
from hashlib import md5

def extract_metadata(pdf_path):
    doc = fitz.open(pdf_path)
    meta = doc.metadata
    title = meta.get('title') or ""
    author = meta.get('author') or ""
    first_page = doc[0].get_text() if len(doc) > 0 else ""
    doi_match = re.search(r"10\.\d{4,9}/[-._;()/:A-Za-z0-9]+", first_page)
    doi = doi_match.group() if doi_match else ""
    year_match = re.search(r"(19|20)\d{2}", first_page)
    year = year_match.group() if year_match else ""
    journal_match = re.search(r"\n([^\n]*?(Rice|Journal|Crop|Agric)[^\n]*?)\n", first_page, re.I)
    journal = journal_match.group(1).strip() if journal_match else ""
    return {
        'title': title,
        'author': author,
        'year': year,
        'doi': doi,
        'journal': journal
    }

def normalize_filename(meta):
    author = meta['author'].split(',')[0] if meta['author'] else 'Unknown'
    year = meta['year'] or 'YYYY'
    title_abbr = re.sub(r'\W+', '', meta['title'])[:20] or 'NoTitle'
    return f"{author}_{year}_{title_abbr}"

def organize_papers(raw_dir, text_dir, output_dir):
    records = []
    seen_keys = set()
    os.makedirs(text_dir, exist_ok=True)
    os.makedirs(output_dir, exist_ok=True)
    for file in os.listdir(raw_dir):
        if not file.lower().endswith('.pdf'): continue
        pdf_path = os.path.join(raw_dir, file)
        meta = extract_metadata(pdf_path)
        base_name = normalize_filename(meta)
        key = f"{meta['doi']}{meta['title']}{meta['author']}"
        hash_key = md5(key.encode()).hexdigest()
        is_dup = hash_key in seen_keys
        if not is_dup:
            seen_keys.add(hash_key)
        new_filename = f"{base_name}.pdf"
        dst_path = os.path.join(text_dir, new_filename)
        shutil.copy(pdf_path, dst_path)
        records.append({
            **meta,
            'src_name': file,
            'dst_name': new_filename,
            'duplicate': is_dup
        })
    df = pd.DataFrame(records)
    df.to_csv(os.path.join(output_dir, "literature_list.csv"), index=False)
    df.to_excel(os.path.join(output_dir, "literature_list.xlsx"), index=False)

if __name__ == "__main__":
    organize_papers(
        raw_dir='../papers_raw',
        text_dir='../papers_text',
        output_dir='../outputs'
    )