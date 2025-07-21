import scrapy
import logging
import re
from langcodes import Language as Lang
from deep_translator import GoogleTranslator
from typing import Dict, List
import os
from openpyxl import Workbook
from langdetect import detect, DetectorFactory
import pandas as pd
from deep_translator.exceptions import TranslationNotFound, RequestError
from scrapy.crawler import CrawlerProcess
from scrapy.utils.project import get_project_settings
from datetime import datetime

DetectorFactory.seed = 0



class TranslationClassifier:
    def __init__(self):

        # Load known drug names from file
        tsv_url = "https://raw.githubusercontent.com/MariaKlap/Drug-Name-Database/refs/heads/main/drug.target.interaction.tsv"
                   

        try:
            df = pd.read_csv(tsv_url, sep='\t')
        except UnicodeDecodeError:
            df = pd.read_csv(tsv_url, sep='\t', encoding='ISO-8859-1')
        print(f"📊 DRUG_NAME column row count (including duplicates and empty): {len(df['DRUG_NAME'])}")

        # Limit to specific columns only
        allowed_columns = {'DRUG_NAME', 'GENE', 'SWISSPROT', 'ACTION_TYPE', 'TARGET_CLASS', 'TARGET_NAME'}
        allowed_columns = [col for col in df.columns if col in allowed_columns]

        terms = set()
        for col in allowed_columns:
            col_terms = df[col].dropna().astype(str)
            col_terms = {t.strip().lower() for t in col_terms if len(t.strip()) > 3}
            terms.update(col_terms)

        self.drug_terms_set = terms
        print(f"✅ Loaded {len(self.drug_terms_set)} drug terms from TSV columns: {', '.join(allowed_columns)}")

        self.DOCUMENT_TYPES = {
            'Announcement': ['announcement', 'notification', 'bulletin'],
            'Expert Report': ['expert report', 'technical report', 'scientific opinion'],
            'Amendment': ['amendment', 'regulation change', 'regulatory update'],
            'Law': ['law', 'legislation', 'statute', 'act'],
            'Directive': ['directive', 'guideline', 'policy'],
            'Order': ['order', 'decision', 'ruling', 'decree'],
            'Information Note': ['information note', 'information bulletin', 'notice'],
            'Q&A': ['questions and answers', 'q&a', 'faq', 'frequently asked'],
            'Instructions': ['instructions', 'manual', 'guidance', 'procedure'],
            'Resolution': ['resolution', 'conclusion', 'determination'],
            'Consultation': ['consultation', 'public hearing', 'stakeholder input'],
            'Product Info': ['product information', 'package leaflet', 'product update'],
            'Regulatory Decision': ['regulatory decision', 'approval summary', 'assessment'],
            'Evaluation': ['evaluation report', 'assessment report', 'review report'],
            'Recommendation': ['recommendation', 'advice', 'suggestion'],
            'Checklist': ['checklist', 'verification list', 'review points'],
            'Approval Tracker': ['approval tracker', 'authorization status', 'timeline'],
            'CHMP Opinion': ['chmp opinion', 'committee opinion', 'scientific opinion'],
            'Committee': ['committee', 'working group', 'task force'],
            'CV': ['curriculum vitae', 'cv', 'resume'],
            'EPAR': ['epar', 'european public assessment report'],
            'Letter': ['letter', 'correspondence', 'official communication'],
            'Meeting': ['meeting', 'conference', 'session'],
            'Withdrawal': ['withdrawn application', 'cancelled submission'],
            'Communication': ['communication', 'announcement', 'message'],
            'Decree': ['decree', 'royal decree', 'official order'],
            'Form': ['form', 'application form', 'submission form'],
            'Regulatory History': ['regulatory history', 'dossier history', 'timeline'],
            'Press Release': ['press release', 'news release', 'media statement'],
            'Ordinance': ['ordinance', 'local regulation', 'municipal law'],
            'Advisory Committee': ['advisory committee', 'committee profile'],
            'Voting': ['voting', 'committee vote', 'decision outcome'],
            'Petition': ['citizen petition', 'public petition', 'request'],
            'Federal Register': ['federal register', 'official gazette', 'journal'],
            'Inspection': ['inspection report', 'audit report', 'site visit'],
            'SOP': ['sop', 'standard procedure', 'operating protocol'],
            'BLA Approval': ['bla', 'biologics license application'],
            'BLA Supplement': ['supplemental bla', 'bla amendment'],
            'NDA Supplement': ['supplemental nda', 'nda amendment'],
            '510(k)': ['510(k)', 'premarket notification'],
            'NDA Approval': ['nda', 'new drug application'],
            'Other Type': []
        }

        self.PRODUCT_TYPES = {
            'Biological': ['biological', 'biologic', 'monoclonal antibody', 'mab', 'recombinant', 'cell therapy',
                           'gene therapy', 'blood product', 'plasma derived', 'therapeutic protein', 'insulin',
                           'erythropoietin', 'immunoglobulin', 'stem cell'],
            'Drug Product': ['drug product', 'finished product', 'formulation', 'dosage form', 'tablet', 'capsule',
                             'injection', 'solution', 'suspension', 'biopharmaceutical', 'biosimilar', 'cream',
                             'ointment', 'gel', 'suppository', 'inhalation'],
            'Drug Substance': ['drug substance', 'active substance', 'api', 'active ingredient', 'bulk drug',
                               'chemical entity', 'reference standard'],
            'Vaccine': ['vaccine', 'vaccination', 'immunization', 'antigen', 'adjuvant', 'mmr', 'dtap', 'hpv',
                        'influenza', 'covid-19', 'sars-cov-2'],
            'Small Molecule': ['small molecule', 'chemical drug', 'synthetic', 'organic compound', 'nme',
                               'new molecular entity', 'low molecular weight'],
            'Medical Device': ['medical device', 'implant', 'stent', 'catheter', 'prosthesis', 'pacemaker',
                               'defibrillator', 'surgical instrument'],
            'IVD': ['ivd', 'in vitro diagnostic', 'diagnostic test', 'assay', 'reagent', 'test kit', 'analyzer',
                    'rapid test'],
            'Other': []
        }


    def translate_to_english(self, text: str, source_lang: str) -> str:
        if not text:
            return text
            
        source_lang = source_lang.lower().strip()
        if source_lang in ["english", "en"]:
            return text
        
        try:
            # Handle Dutch specifically
            if source_lang in ["dutch", "nl"]:
                lang_code = "nl"
            else:
                lang_code = Lang.get(source_lang).to_alpha2()
                
            translated = GoogleTranslator(source=lang_code, target='en').translate(text)
            return translated
        except Exception as e:
            logging.warning(f"Translation failed: {str(e)}")
            return "[Translation Not Available]"

    def classify_document(self, text: str) -> Dict[str, str]:
        text = text.lower()
        for doc_type, keywords in self.DOCUMENT_TYPES.items():
            if any(re.search(rf'\b{re.escape(kw)}\b', text) for kw in keywords):
                return {'document_type': doc_type}
        return {'document_type': 'Other Type'}

    def classify_product(self, text: str) -> Dict[str, str]:
        text_lower = text.lower()
        drug_names = self.extract_drug_names(text)
        for product_type, keywords in self.PRODUCT_TYPES.items():
            if any(re.search(rf'\b{re.escape(kw)}\b', text_lower) for kw in keywords):
                return {
                    'product_type': product_type,
                    'drug_names': ", ".join(drug_names) if drug_names else "None"
                }
        return {
            'product_type': 'Drug Product' if drug_names else 'Other',
            'drug_names': ", ".join(drug_names) if drug_names else "None"
        }

    def extract_drug_names(self, text: str) -> List[str]:
        if not text.strip():
            return []

        matched = []
        for term in self.drug_terms_set:
            # Escape regex special chars and match as whole word/phrase
            pattern = r'(?<!\w)' + re.escape(term.lower()) + r'(?!\w)'
            if re.search(pattern, text, flags=re.IGNORECASE):
                matched.append(term)
        return matched


class CBGfinal5Spider(scrapy.Spider):
    name = 'CBGfinal5'
    start_urls = ['https://www.cbg-meb.nl/actueel/nieuws?']
    max_pages = 2

    def __init__(self):
        self.classifier = TranslationClassifier()
        self.FASTTEXT_MODEL = None

        self.wb = Workbook()
        self.ws = self.wb.active
        self.ws.append([
            'Title',
            'Summary',
            'Article URL',
            'Date',
            'Document_Type',
            'Product_Type',
            'Countries',
            'Regions',
            'Drug_names',
            'Language',
            'Source URL',
            'title_english',
            'summary_english'
        ])
        super().__init__()

    def closed(self, reason):
        output_path = os.path.join(os.getcwd(), 'CBGnews_items.xlsx')
        self.wb.save(output_path)
        self.logger.info(f"Excel file saved to {output_path}")

    def detect_language(self, text: str) -> str:
        """Detect language of given text with improved Dutch handling"""
        if not text or len(text.strip()) < 3:
            return "Unknown"
        
        try:
            lang_code = detect(text)
            # Special handling for Dutch
            if lang_code == 'nl':
                return "Dutch"
            return Lang.get(lang_code).display_name()
        except Exception as e:
            logging.debug(f"Language detection failed: {str(e)}")
            return "Unknown"

    def detect_countries(self, text: str) -> Dict[str, str]:
        text_lower = text.lower()
        COUNTRY_PATTERNS = {
            'Netherlands': ['netherlands', 'nederland', 'dutch', 'amsterdam'],
            'European Union': ['european union', 'eu', 'brussels'],
        }
        countries = [country for country, patterns in COUNTRY_PATTERNS.items()
                     if any(pat in text_lower for pat in patterns)]
        regions = ['Western Europe'] if 'Netherlands' in countries else []
        return {
            'mentioned_countries': ", ".join(countries) if countries else "None",
            'mentioned_regions': ", ".join(regions) if regions else "None"
        }

    def generate_summary(self, text: str) -> str:
        if not text.strip():
            return "No content"
        sentences = re.split(r'[.!?]', text)
        return ' '.join(sentences[:3]) + '...'

    def parse(self, response):
        items = response.css('li.results__item')
        if items:
            for item in items:
                title = item.css('h3::text').get(default="").strip()
                content = item.css('p:not(.meta)::text').get(default="").strip()
               # Extract and format the date
                raw_date = item.css('p.meta::text').get(default="").strip().split()[2]
                
                # Normalize various formats to dd/mm/yyyy
                parsed_date = raw_date  # fallback
                for fmt in ("%d-%m-%Y", "%d.%m.%Y", "%d/%m/%Y", "%Y-%m-%d"):
                    try:
                        parsed_date = datetime.strptime(raw_date, fmt).strftime("%d/%m/%Y")
                        break
                    except ValueError:
                        continue


                url = response.urljoin(item.css('a::attr(href)').get())

                # Improved language detection
                raw_text = f"{title} {content}".strip()
                lang = "Unknown"
                try:
                    if len(raw_text) >= 10:
                        lang = self.detect_language(raw_text)
                    elif len(title) >= 3:
                        lang = self.detect_language(title)
                except Exception as e:
                    logging.warning(f"Language detection error: {str(e)}")

                # Translate both title and content
                title_en = self.classifier.translate_to_english(title, lang)
                content_en = self.classifier.translate_to_english(content, lang)

                # Generate summary in Dutch (original)
                summary = self.generate_summary(content)

                # (Optional) If you want a separate summary_english:
                summary_english = self.generate_summary(content_en)


                doc_info = self.classifier.classify_document(f"{title_en} {content_en}")
                product_info = self.classifier.classify_product(f"{title_en} {content_en}")
                country_info = self.detect_countries(f"{title_en} {content_en}")

                self.ws.append([
                self.ws.append([
                    title,
                    summary, 
                    url,
                    parsed_date,  # <-- use the formatted date
                    doc_info['document_type'],
                    product_info['product_type'],
                    country_info['mentioned_countries'],
                    country_info['mentioned_regions'],
                    product_info['drug_names'],
                    lang,
                    self.start_urls[0],
                    title_en,
                    content_en
                ])


            # Pagination
            current_page = int(response.url.split('pagina=')[1]) if 'pagina=' in response.url else 1
            if current_page < self.max_pages:
                next_page = current_page + 1
                next_url = f'https://www.cbg-meb.nl/actueel/nieuws?pagina={next_page}'
                yield response.follow(next_url, callback=self.parse)

if __name__ == "__main__":
    process = CrawlerProcess()
    process.crawl(CBGfinal5Spider)
    process.start()

