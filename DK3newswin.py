import scrapy
import logging
import re
from langcodes import Language as Lang
import fasttext
from langdetect import detect, DetectorFactory
from deep_translator import GoogleTranslator
from typing import Dict, List
import os
import dateparser
from typing import List
from openpyxl import Workbook
from openpyxl.styles import Font
from scrapy import signals
from scrapy.crawler import CrawlerProcess
import time
import random
import pandas as pd

# Initialize language detection
DetectorFactory.seed = 0
    
class TranslationClassifier:
    """Handles translation and classification of text"""

    def load_known_drugs(self, filepath: str) -> List[str]:
        try:
            df = pd.read_csv(filepath, sep='\t')
            logging.info(f"Loaded {len(df)} rows from {filepath}")

            terms = set()
            for col in df.columns:
                col_terms = (
                    df[col]
                    .dropna()
                    .astype(str)
                    .str.strip()
                    .str.lower()
                    .tolist()
                )
                for term in col_terms:
                    if len(term) > 3:  # only keep terms longer than 3 characters
                        terms.add(term)

            return sorted(terms)

        except Exception as e:
            logging.error(f"Error loading known drug terms: {e}")
            return []


    
    def __init__(self):
        # ✅ LOAD drug terms from .tsv file
        tsv_path = 'https://raw.githubusercontent.com/MariaKlap/Drug-Name-Database/refs/heads/main/drug.target.interaction.tsv'  
        

        try:
            df = pd.read_csv(tsv_path, sep='\t')
        except UnicodeDecodeError:
            df = pd.read_csv(tsv_path, sep='\t', encoding='ISO-8859-1')
        print(f"📊 DRUG_NAME column row count (including duplicates and empty): {len(df['DRUG_NAME'])}")

        # Limit to specific columns only
        allowed_columns = {'DRUG_NAME', 'SWISSPROT', 'ACTION_TYPE', 'TARGET_CLASS', 'TARGET_NAME'}
        allowed_columns = [col for col in df.columns if col in allowed_columns]

        terms = set()
        for col in allowed_columns:
            col_terms = df[col].dropna().astype(str)
            col_terms = {t.strip().lower() for t in col_terms if len(t.strip()) > 3}
            terms.update(col_terms)

        self.drug_terms_set = terms
        print(f"✅ Loaded {len(self.drug_terms_set)} drug terms from TSV columns: {', '.join(allowed_columns)}")


                        
        # English-only document type classification
        self.DOCUMENT_TYPES = {
            'Announcement': ['announcement', 'notification', 'bulletin'],
            'Expert Report': ['expert report', 'technical report', 'scientific opinion'],
            'Amendment': ['amendment', 'regulation change', 'regulatory update'],
            'Law': ['law', 'legislation', 'statute'],
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
            'NDA Approval': ['new drug application'],
            'Other Type': []
        }

        # English-only product type classification
        self.PRODUCT_TYPES = {
            'Biological': [
                'biological', 'biologic',
                'monoclonal antibody', 'mab', 'recombinant', 'cell therapy',
                'gene therapy', 'blood product', 'plasma derived',
                'therapeutic protein', 'insulin', 'erythropoietin',
                'immunoglobulin', 'stem cell'
            ],
            'Drug Product': [
                'drug product', 'finished product', 'formulation', 'dosage form',
                'tablet', 'capsule', 'injection', 'solution', 'suspension', 'biopharmaceutical', 'biosimilar',
                'cream', 'ointment', 'gel', 'suppository', 'inhalation'
            ],
            'Drug Substance': [
                'drug substance', 'active substance', 'api', 'active ingredient',
                'bulk drug', 'chemical entity', 'reference standard'
            ],
            'Vaccine': [
                'vaccine', 'vaccination', 'immunization', 'antigen', 'adjuvant',
                'mmr', 'dtap', 'hpv', 'influenza', 'covid-19', 'sars-cov-2'
            ],
            'Small Molecule': [
                'small molecule', 'chemical drug', 'synthetic', 'organic compound',
                'nme', 'new molecular entity', 'low molecular weight'
            ],
            'Medical Device': [
                'medical device', 'implant', 'stent', 'catheter', 'prosthesis',
                'pacemaker', 'defibrillator', 'surgical instrument'
            ],
            'IVD': [
                'ivd', 'in vitro diagnostic', 'diagnostic test', 'assay',
                'reagent', 'test kit', 'analyzer', 'rapid test'
            ],
            'Other': []
        }
    
    def preprocess_text(self, text: str) -> str:
        """Clean text for better NER performance"""
        if not text:
            return ""
        
        # Remove excessive whitespace
        text = ' '.join(text.split())
        
        # Handle common drug patterns
        text = re.sub(r'(\d+)\s*(mg|ml|g)\b', r'\1\2', text)  # "100 mg" -> "100mg"
        
        return text

    def translate_to_english(self, text: str, source_lang: str) -> str:
        """Safely translate text to English using iso639 for language code conversion"""
        if not text or source_lang.lower() == 'english':
            return text
            
        try:
            # Get language code from full language name using iso639
            lang_code = Lang(name=source_lang).part1
            if not lang_code:
                logging.warning(f"No ISO639-1 code found for language: {source_lang}")
                return text
                
            return GoogleTranslator(source=lang_code, target='en').translate(text)
        except Exception as e:
            logging.warning(f"Translation failed: {source_lang} --> {str(e)}")
            return text

    def classify_document(self, text: str) -> Dict[str, str]:
        """Classify document type from English text"""
        text = self.preprocess_text(text).lower()
        for doc_type, keywords in self.DOCUMENT_TYPES.items():
            matched = [kw for kw in keywords if re.search(rf'\b{re.escape(kw)}\b', text)]
            if matched:
                return {
                    'document_type': doc_type,
                    'matched_keywords': ", ".join(matched)
                }
        return {'document_type': 'Other Type', 'matched_keywords': 'unclassified'}
    
    def extract_drug_names(self, text: str) -> List[str]:
        if not text.strip():
            return []

        matched = []
        for term in self.drug_terms_set:
            # Escape regex special chars and match as whole word/phrase
            pattern = r'\b' + re.escape(term) + r'\b'
            if re.search(pattern, text, flags=re.IGNORECASE):
                matched.append(term)
        return matched

    def classify_product(self, text: str) -> Dict[str, str]:
        text_lower = self.preprocess_text(text).lower()
        drug_names = self.extract_drug_names(text) or []  # Ensure drug_names is never None
        
        product_info = {
            'product_type': 'Other',
            'product_keywords': 'unclassified',
            'drug_names': ", ".join(drug_names) if drug_names else None,
            'classification_text': text
        }

        # First check for specific product types
        for product_type, keywords in self.PRODUCT_TYPES.items():
            if product_type == 'Drug Product':
                continue  # We'll handle this separately
        
            matched = [kw for kw in keywords if re.search(rf'\b{re.escape(kw)}\b', text_lower)]
            if matched:
                product_info.update({
                    'product_type': product_type,
                    'product_keywords': ", ".join(matched)
                })
                return product_info
    
        # If no specific type matched but we found drug names, classify as Drug Product
        if drug_names:
            return {
                'product_type': 'Drug Product',
                'product_keywords': f"Identified drug names: {', '.join(drug_names)}",
                'drug_names': ", ".join(drug_names)
            }
    
        # Default case
        return {
            'product_type': 'Other',
            'product_keywords': 'unclassified',
            'drug_names': None,
            'classification_text': text
        }

class DK1Spider(scrapy.Spider):
    name = 'DK3'
    start_urls = ['https://laegemiddelstyrelsen.dk/da/nyheder/']
    max_pages = 2
    current_page = 1

    custom_settings = {
        'DOWNLOAD_DELAY': 3.0,  # Increased delay
        'DOWNLOAD_TIMEOUT': 60,  # Longer timeout
        'USER_AGENT': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'CONCURRENT_REQUESTS': 4,  # Fixed typo
        'ROBOTSTXT_OBEY': True,
        'RETRY_TIMES': 5,  # Increased retries
        'RETRY_HTTP_CODES': [500, 502, 503, 504, 408, 429],
        'HTTPCACHE_ENABLED': True,
        'REACTOR_THREADPOOL_MAXSIZE': 4
    }
    
    # Country patterns for detection in text
    COUNTRY_PATTERNS = {
        # Europe (Complete list)
        'Albania': ['albania', 'shqipëria', 'tirana'],
        'Andorra': ['andorra', 'andorre'],
        'Austria': ['austria', 'österreich', 'vienna'],
        'Belarus': ['belarus', 'belarús', 'minsk'],
        'Belgium': ['belgium', 'belgique', 'belgie', 'brussels'],
        'Bosnia and Herzegovina': ['bosnia', 'herzegovina', 'sarajevo'],
        'Bulgaria': ['bulgaria', 'българия', 'sofia'],
        'Croatia': ['croatia', 'hrvatska', 'zagreb'],
        'Cyprus': ['cyprus', 'κύπρος', 'lefkosia'],
        'Czech Republic': ['czech republic', 'česko', 'prague'],
        'Denmark': ['denmark', 'danmark', 'copenhagen'],
        'Estonia': ['estonia', 'eesti', 'tallinn'],
        'Finland': ['finland', 'suomi', 'helsinki'],
        'France': ['france', 'french', 'paris'],
        'Germany': ['germany', 'deutschland', 'berlin'],
        'Greece': ['greece', 'ελλάδα', 'athens'],
        'Hungary': ['hungary', 'magyarország', 'budapest'],
        'Iceland': ['iceland', 'ísland', 'reykjavik'],
        'Ireland': ['ireland', 'éire', 'dublin'],
        'Italy': ['italy', 'italia', 'rome'],
        'Latvia': ['latvia', 'latvija', 'riga'],
        'Liechtenstein': ['liechtenstein', 'vaduz'],
        'Lithuania': ['lithuania', 'lietuva', 'vilnius'],
        'Luxembourg': ['luxembourg', 'luxemburg', 'luxembourg city'],
        'Malta': ['malta', 'valletta'],
        'Moldova': ['moldova', 'chișinău'],
        'Monaco': ['monaco', 'monaco-ville'],
        'Montenegro': ['montenegro', 'crna gora', 'podgorica'],
        'Netherlands': ['netherlands', 'nederland', 'holland', 'amsterdam'],
        'North Macedonia': ['north macedonia', 'macedonia', 'skopje'],
        'Norway': ['norway', 'norge', 'oslo'],
        'Poland': ['poland', 'polska', 'warsaw'],
        'Portugal': ['portugal', 'lisbon'],
        'Romania': ['romania', 'românia', 'bucharest'],
        'Russia': ['russia', 'россия', 'moscow'],
        'San Marino': ['san marino'],
        'Serbia': ['serbia', 'srbija', 'belgrade'],
        'Slovakia': ['slovakia', 'slovensko', 'bratislava'],
        'Slovenia': ['slovenia', 'slovenija', 'ljubljana'],
        'Spain': ['spain', 'españa', 'madrid'],
        'Sweden': ['sweden', 'sverige', 'stockholm'],
        'Switzerland': ['switzerland', 'suisse', 'schweiz', 'bern'],
        'Ukraine': ['ukraine', 'україна', 'kyiv'],
        'United Kingdom': ['uk', 'united kingdom', 'britain', 'london'],
        'Vatican City': ['vatican', 'holy see'],

        # Americas (Complete list)
        'Antigua and Barbuda': ['antigua', 'barbuda', "antigua and barbuda", 'saint john'],
        'Argentina': ['argentina', 'buenos aires', 'argentine republic'],
        'Bahamas': ['bahamas', 'nassau', 'commonwealth of the bahamas'],
        'Barbados': ['barbados', 'bridgetown'],
        'Belize': ['belize', 'belmopan'],
        'Bolivia': ['bolivia', 'sucre', 'la paz', 'plurinational state'],
        'Brazil': ['brazil', 'brasil', 'brasília', 'rio de janeiro', 'federative republic'],
        'Canada': ['canada', 'ottawa', 'toronto', 'ontario', 'quebec'],
        'Chile': ['chile', 'santiago', 'republic of chile'],
        'Colombia': ['colombia', 'bogotá', 'bogota', 'republic of colombia'],
        'Costa Rica': ['costa rica', 'san josé', 'san jose'],
        'Cuba': ['cuba', 'havana', 'republic of cuba'],
        'Dominica': ['dominica', 'roseau', 'commonwealth of dominica'],
        'Dominican Republic': ['dominican republic', 'santo domingo'],
        'Ecuador': ['ecuador', 'quito', 'republic of ecuador'],
        'El Salvador': ['el salvador', 'san salvador', 'republic of el salvador'],
        'Grenada': ['grenada', "saint george"],
        'Guatemala': ['guatemala', 'guatemala city', 'republic of guatemala'],
        'Guyana': ['guyana', 'georgetown', 'cooperative republic'],
        'Haiti': ['haiti', 'port-au-prince', 'republic of haiti'],
        'Honduras': ['honduras', 'tegucigalpa', 'republic of honduras'],
        'Jamaica': ['jamaica', 'kingston'],
        'Mexico': ['mexico', 'méxico', 'mexico city', 'cdmx', 'estados unidos mexicanos'],
        'Nicaragua': ['nicaragua', 'managua', 'republic of nicaragua'],
        'Panama': ['panama', 'panama city', 'republic of panama'],
        'Paraguay': ['paraguay', 'asunción', 'asunción', 'republic of paraguay'],
        'Peru': ['peru', 'lima', 'republic of peru'],
        'Saint Kitts and Nevis': ['saint kitts', 'nevis', 'basseterre'],
        'Saint Lucia': ['saint lucia', 'castries'],
        'Saint Vincent and the Grenadines': ['saint vincent', 'grenadines', 'kingstown'],
        'Suriname': ['suriname', 'paramaribo', 'republic of suriname'],
        'Trinidad and Tobago': ['trinidad', 'tobago', 'port of spain'],
        'United States': ['usa', 'u\\.s\\.', 'united states', 'america', 'washington dc', 'new york', 'california'],
        'Uruguay': ['uruguay', 'montevideo', 'oriental republic'],
        'Venezuela': ['venezuela', 'caracas', 'bolivarian republic'],

        # Asia (Complete list)
        'Afghanistan': ['afghanistan', 'kabul', 'islamic emirate'],
        'Armenia': ['armenia', 'yerevan', 'republic of armenia'],
        'Azerbaijan': ['azerbaijan', 'baku', 'republic of azerbaijan'],
        'Bahrain': ['bahrain', 'manama', 'kingdom of bahrain'],
        'Bangladesh': ['bangladesh', 'dhaka', "people's republic"],
        'Bhutan': ['bhutan', 'thimphu', 'kingdom of bhutan'],
        'Brunei': ['brunei', 'bandar seri begawan', 'darussalam'],
        'Cambodia': ['cambodia', 'phnom penh', 'kingdom of cambodia'],
        'China': ['china', 'zhongguo', 'beijing', 'shanghai', "people's republic"],
        'Cyprus': ['cyprus', 'nicosia', 'republic of cyprus'],
        'Georgia': ['georgia', 'tbilisi'],
        'India': ['india', 'bharat', 'new delhi', 'mumbai', 'republic of india'],
        'Indonesia': ['indonesia', 'jakarta', 'republic of indonesia'],
        'Iran': ['iran', 'tehran', 'islamic republic'],
        'Iraq': ['iraq', 'baghdad', 'republic of iraq'],
        'Israel': ['israel', 'jerusalem', 'state of israel'],
        'Japan': ['japan', 'nippon', 'tokyo'],
        'Jordan': ['jordan', 'amman', 'hashemite kingdom'],
        'Kazakhstan': ['kazakhstan', 'nur-sultan', 'astana', 'republic of kazakhstan'],
        'Kuwait': ['kuwait', 'kuwait city', 'state of kuwait'],
        'Kyrgyzstan': ['kyrgyzstan', 'bishkek', 'kyrgyz republic'],
        'Laos': ['laos', 'vientiane', "lao people's republic"],
        'Lebanon': ['lebanon', 'beirut', 'lebanese republic'],
        'Malaysia': ['malaysia', 'kuala lumpur', 'putrajaya'],
        'Maldives': ['maldives', 'malé', 'republic of maldives'],
        'Mongolia': ['mongolia', 'ulaanbaatar'],
        'Myanmar': ['myanmar', 'burma', 'naypyidaw', 'republic of the union'],
        'Nepal': ['nepal', 'kathmandu', 'federal democratic republic'],
        'North Korea': ['north korea', 'dprk', 'pyongyang', "democratic people's republic"],
        'Oman': ['oman', 'muscat', 'sultanate of oman'],
        'Pakistan': ['pakistan', 'islamabad', 'islamic republic'],
        'Palestine': ['palestine', 'ramallah', 'state of palestine'],
        'Philippines': ['philippines', 'manila', 'republic of the philippines'],
        'Qatar': ['qatar', 'doha', 'state of qatar'],
        'Russia': ['russia', 'russian federation', 'moscow'],
        'Saudi Arabia': ['saudi arabia', 'riyadh', 'kingdom of saudi arabia'],
        'Singapore': ['singapore', 'republic of singapore'],
        'South Korea': ['south korea', 'korea republic', 'seoul', 'republic of korea'],
        'Sri Lanka': ['sri lanka', 'colombo', 'sri jayawardenepura kotte'],
        'Syria': ['syria', 'damascus', 'syrian arab republic'],
        'Taiwan': ['taiwan', 'taipei', 'republic of china'],
        'Tajikistan': ['tajikistan', 'dushanbe', 'republic of tajikistan'],
        'Thailand': ['thailand', 'bangkok', 'kingdom of thailand'],
        'Timor-Leste': ['timor-leste', 'east timor', 'dili', 'democratic republic'],
        'Turkey': ['turkey', 'türkiye', 'ankara', 'republic of turkey'],
        'Turkmenistan': ['turkmenistan', 'ashgabat'],
        'United Arab Emirates': ['uae', 'united arab emirates', 'dubai', 'abu dhabi'],
        'Uzbekistan': ['uzbekistan', 'tashkent', 'republic of uzbekistan'],
        'Vietnam': ['vietnam', 'hanoi', 'socialist republic'],
        'Yemen': ['yemen', "sana'a", 'republic of yemen'],

        # Africa (Complete list)
        'Algeria': ['algeria', 'algiers', "people's democratic republic"],
        'Angola': ['angola', 'luanda', 'republic of angola'],
        'Benin': ['benin', 'porto-novo', 'republic of benin'],
        'Botswana': ['botswana', 'gaborone', 'republic of botswana'],
        'Burkina Faso': ['burkina faso', 'ouagadougou'],
        'Burundi': ['burundi', 'gitega', 'republic of burundi'],
        'Cameroon': ['cameroon', 'yaoundé', 'republic of cameroon'],
        'Cape Verde': ['cape verde', 'cabo verde', 'praia', 'republic of cape verde'],
        'Central African Republic': ['central african republic', 'bangui'],
        'Chad': ['chad', "n'djamena", 'republic of chad'],
        'Comoros': ['comoros', 'moroni', 'union of the comoros'],
        'Congo (Brazzaville)': ['republic of the congo', 'congo-brazzaville', 'brazzaville'],
        'Congo (Kinshasa)': ['democratic republic of the congo', 'drc', 'kinshasa'],
        "Côte d'Ivoire": ["côte d'ivoire", 'ivory coast', 'yamoussoukro'],
        'Djibouti': ['djibouti', 'republic of djibouti'],
        'Egypt': ['egypt', 'cairo', 'arab republic of egypt'],
        'Equatorial Guinea': ['equatorial guinea', 'malabo', 'republic of equatorial guinea'],
        'Eritrea': ['eritrea', 'asmara', 'state of eritrea'],
        'Eswatini': ['eswatini', 'swaziland', 'mbabane', 'kingdom of eswatini'],
        'Ethiopia': ['ethiopia', 'addis ababa', 'federal democratic republic'],
        'Gabon': ['gabon', 'libreville', 'gabonese republic'],
        'Gambia': ['gambia', 'banjul', 'republic of the gambia'],
        'Ghana': ['ghana', 'accra', 'republic of ghana'],
        'Guinea': ['guinea', 'conakry', 'republic of guinea'],
        'Guinea-Bissau': ['guinea-bissau', 'bissau', 'republic of guinea-bissau'],
        'Kenya': ['kenya', 'nairobi', 'republic of kenya'],
        'Lesotho': ['lesotho', 'maseru', 'kingdom of lesotho'],
        'Liberia': ['liberia', 'monrovia', 'republic of liberia'],
        'Libya': ['libya', 'tripoli', 'state of libya'],
        'Madagascar': ['madagascar', 'antananarivo', 'republic of madagascar'],
        'Malawi': ['malawi', 'lilongwe', 'republic of malawi'],
        'Mali': ['mali', 'bamako', 'republic of mali'],
        'Mauritania': ['mauritania', 'nouakchott', 'islamic republic'],
        'Mauritius': ['mauritius', 'port louis', 'republic of mauritius'],
        'Morocco': ['morocco', 'rabat', 'kingdom of morocco'],
        'Mozambique': ['mozambique', 'maputo', 'republic of mozambique'],
        'Namibia': ['namibia', 'windhoek', 'republic of namibia'],
        'Niger': ['niger', 'niamey', 'republic of niger'],
        'Nigeria': ['nigeria', 'abuja', 'federal republic of nigeria'],
        'Rwanda': ['rwanda', 'kigali', 'republic of rwanda'],
        'Sao Tome and Principe': ['são tomé and príncipe', 'sao tome', 'são tomé'],
        'Senegal': ['senegal', 'dakar', 'republic of senegal'],
        'Seychelles': ['seychelles', 'victoria', 'republic of seychelles'],
        'Sierra Leone': ['sierra leone', 'freetown', 'republic of sierra leone'],
        'Somalia': ['somalia', 'mogadishu', 'federal republic of somalia'],
        'South Africa': ['south africa', 'pretoria', 'cape town', 'republic of south africa'],
        'South Sudan': ['south sudan', 'juba', 'republic of south sudan'],
        'Sudan': ['sudan', 'khartoum', 'republic of the sudan'],
        'Tanzania': ['tanzania', 'dodoma', 'united republic of tanzania'],
        'Togo': ['togo', 'lomé', 'togolese republic'],
        'Tunisia': ['tunisia', 'tunis', 'republic of tunisia'],
        'Uganda': ['uganda', 'kampala', 'republic of uganda'],
        'Zambia': ['zambia', 'lusaka', 'republic of zambia'],
        'Zimbabwe': ['zimbabwe', 'harare', 'republic of zimbabwe'],

        # International/Regional
        'European Union': ['eu', 'european union', 'e\\.u\\.', 'brussels eu'],
        'African Union': ['african union', 'au', 'addis ababa'],
        'ASEAN': ['asean', 'southeast asia', 'jakarta'],
        'Global': ['who', 'world health organization', 'united nations', 'international'],
    }

    # Mapping of regions to countries
    REGION_MAPPING = {
        # Europe
        'Albania': 'Southern Europe',
        'Andorra': 'Southern Europe',
        'Austria': 'Central Europe',
        'Belarus': 'Eastern Europe',
        'Belgium': 'Western Europe',
        'Bosnia and Herzegovina': 'Southern Europe',
        'Bulgaria': 'Eastern Europe',
        'Croatia': 'Southern Europe',
        'Cyprus': 'Southern Europe',
        'Czech Republic': 'Central Europe',
        'Denmark': 'Northern Europe',
        'Estonia': 'Northern Europe',
        'Finland': 'Northern Europe',
        'France': 'Western Europe',
        'Germany': 'Central Europe',
        'Greece': 'Southern Europe',
        'Hungary': 'Central Europe',
        'Iceland': 'Northern Europe',
        'Ireland': 'Northern Europe',
        'Italy': 'Southern Europe',
        'Latvia': 'Northern Europe',
        'Liechtenstein': 'Central Europe',
        'Lithuania': 'Northern Europe',
        'Luxembourg': 'Western Europe',
        'Malta': 'Southern Europe',
        'Moldova': 'Eastern Europe',
        'Monaco': 'Western Europe',
        'Montenegro': 'Southern Europe',
        'Netherlands': 'Western Europe',
        'North Macedonia': 'Southern Europe',
        'Norway': 'Northern Europe',
        'Poland': 'Central Europe',
        'Portugal': 'Southern Europe',
        'Romania': 'Eastern Europe',
        'Russia': 'Eastern Europe',  # Transcontinental
        'San Marino': 'Southern Europe',
        'Serbia': 'Southern Europe',
        'Slovakia': 'Central Europe',
        'Slovenia': 'Southern Europe',
        'Spain': 'Southern Europe',
        'Sweden': 'Northern Europe',
        'Switzerland': 'Central Europe',
        'Ukraine': 'Eastern Europe',
        'United Kingdom': 'Northern Europe',
        'Vatican City': 'Southern Europe',

        # Americas
        # North America
        'Canada': 'North America',
        'United States': 'North America',
        'Mexico': 'North America',
        
        # Central America
        'Belize': 'Central America',
        'Costa Rica': 'Central America',
        'El Salvador': 'Central America',
        'Guatemala': 'Central America',
        'Honduras': 'Central America',
        'Nicaragua': 'Central America',
        'Panama': 'Central America',
        
        # Caribbean
        'Antigua and Barbuda': 'Caribbean',
        'Bahamas': 'Caribbean',
        'Barbados': 'Caribbean',
        'Cuba': 'Caribbean',
        'Dominica': 'Caribbean',
        'Dominican Republic': 'Caribbean',
        'Grenada': 'Caribbean',
        'Haiti': 'Caribbean',
        'Jamaica': 'Caribbean',
        'Saint Kitts and Nevis': 'Caribbean',
        'Saint Lucia': 'Caribbean',
        'Saint Vincent and the Grenadines': 'Caribbean',
        'Trinidad and Tobago': 'Caribbean',
        
        # South America
        'Argentina': 'South America',
        'Bolivia': 'South America',
        'Brazil': 'South America',
        'Chile': 'South America',
        'Colombia': 'South America',
        'Ecuador': 'South America',
        'Guyana': 'South America',
        'Paraguay': 'South America',
        'Peru': 'South America',
        'Suriname': 'South America',
        'Uruguay': 'South America',
        'Venezuela': 'South America',

        # Asia
        # Central Asia
        'Kazakhstan': 'Central Asia',
        'Kyrgyzstan': 'Central Asia',
        'Tajikistan': 'Central Asia',
        'Turkmenistan': 'Central Asia',
        'Uzbekistan': 'Central Asia',
        
        # East Asia
        'China': 'East Asia',
        'Japan': 'East Asia',
        'Mongolia': 'East Asia',
        'North Korea': 'East Asia',
        'South Korea': 'East Asia',
        'Taiwan': 'East Asia',
        
        # South Asia
        'Afghanistan': 'South Asia',
        'Bangladesh': 'South Asia',
        'Bhutan': 'South Asia',
        'India': 'South Asia',
        'Maldives': 'South Asia',
        'Nepal': 'South Asia',
        'Pakistan': 'South Asia',
        'Sri Lanka': 'South Asia',
        
        # Southeast Asia
        'Brunei': 'Southeast Asia',
        'Cambodia': 'Southeast Asia',
        'Indonesia': 'Southeast Asia',
        'Laos': 'Southeast Asia',
        'Malaysia': 'Southeast Asia',
        'Myanmar': 'Southeast Asia',
        'Philippines': 'Southeast Asia',
        'Singapore': 'Southeast Asia',
        'Thailand': 'Southeast Asia',
        'Timor-Leste': 'Southeast Asia',
        'Vietnam': 'Southeast Asia',
        
        # Middle East (West Asia)
        'Armenia': 'Middle East',
        'Azerbaijan': 'Middle East',
        'Bahrain': 'Middle East',
        'Cyprus': 'Middle East',
        'Georgia': 'Middle East',
        'Iran': 'Middle East',
        'Iraq': 'Middle East',
        'Israel': 'Middle East',
        'Jordan': 'Middle East',
        'Kuwait': 'Middle East',
        'Lebanon': 'Middle East',
        'Oman': 'Middle East',
        'Palestine': 'Middle East',
        'Qatar': 'Middle East',
        'Saudi Arabia': 'Middle East',
        'Syria': 'Middle East',
        'Turkey': 'Middle East',
        'United Arab Emirates': 'Middle East',
        'Yemen': 'Middle East',

        # ====== AFRICA ====== #
        # Northern Africa
        'Algeria': 'Northern Africa',
        'Egypt': 'Northern Africa',
        'Libya': 'Northern Africa',
        'Morocco': 'Northern Africa',
        'Sudan': 'Northern Africa',
        'Tunisia': 'Northern Africa',
        
        # Sub-Saharan Africa
        # Western Africa
        'Benin': 'Western Africa',
        'Burkina Faso': 'Western Africa',
        'Cape Verde': 'Western Africa',
        "Côte d'Ivoire": 'Western Africa',
        'Gambia': 'Western Africa',
        'Ghana': 'Western Africa',
        'Guinea': 'Western Africa',
        'Guinea-Bissau': 'Western Africa',
        'Liberia': 'Western Africa',
        'Mali': 'Western Africa',
        'Mauritania': 'Western Africa',
        'Niger': 'Western Africa',
        'Nigeria': 'Western Africa',
        'Senegal': 'Western Africa',
        'Sierra Leone': 'Western Africa',
        'Togo': 'Western Africa',
        
        # Central Africa
        'Angola': 'Central Africa',
        'Cameroon': 'Central Africa',
        'Central African Republic': 'Central Africa',
        'Chad': 'Central Africa',
        'Congo (Brazzaville)': 'Central Africa',
        'Congo (Kinshasa)': 'Central Africa',
        'Equatorial Guinea': 'Central Africa',
        'Gabon': 'Central Africa',
        'Sao Tome and Principe': 'Central Africa',
        
        # Eastern Africa
        'Burundi': 'Eastern Africa',
        'Comoros': 'Eastern Africa',
        'Djibouti': 'Eastern Africa',
        'Eritrea': 'Eastern Africa',
        'Ethiopia': 'Eastern Africa',
        'Kenya': 'Eastern Africa',
        'Madagascar': 'Eastern Africa',
        'Malawi': 'Eastern Africa',
        'Mauritius': 'Eastern Africa',
        'Mozambique': 'Eastern Africa',
        'Rwanda': 'Eastern Africa',
        'Seychelles': 'Eastern Africa',
        'Somalia': 'Eastern Africa',
        'South Sudan': 'Eastern Africa',
        'Tanzania': 'Eastern Africa',
        'Uganda': 'Eastern Africa',
        'Zambia': 'Eastern Africa',
        'Zimbabwe': 'Eastern Africa',
        
        # Southern Africa
        'Botswana': 'Southern Africa',
        'Eswatini': 'Southern Africa',
        'Lesotho': 'Southern Africa',
        'Namibia': 'Southern Africa',
        'South Africa': 'Southern Africa',

        # Oceania
        'Australia': 'Australia and New Zealand',
        'New Zealand': 'Australia and New Zealand',
        'Fiji': 'Pacific Islands',
        'Papua New Guinea': 'Pacific Islands',
        'Solomon Islands': 'Pacific Islands',
        'Vanuatu': 'Pacific Islands',

        # Special Regions
        'European Union': 'European Union',
        'African Union': 'African Union',
        'ASEAN': 'ASEAN',
        'Global': 'Global'
    }

    # Mapping of languages to likely countries
    LANGUAGE_TO_COUNTRY = {
        # European Languages
        'dutch': 'Netherlands', 'flemish': 'Belgium',
        'german': 'Germany', 'austrian german': 'Austria',
        'swiss german': 'Switzerland', 'french': 'France',
        'belgian french': 'Belgium', 'swiss french': 'Switzerland',
        'canadian french': 'Canada', 'italian': 'Italy',
        'swiss italian': 'Switzerland', 'spanish': 'Spain',
        'latin american spanish': 'Mexico', 'catalan': 'Spain',
        'portuguese': 'Portugal', 'brazilian portuguese': 'Brazil',
        'english': 'United States', 'british english': 'United Kingdom',
        'irish english': 'Ireland', 'scots': 'United Kingdom',
        'swedish': 'Sweden', 'norwegian': 'Norway',
        'danish': 'Denmark', 'finnish': 'Finland',
        'icelandic': 'Iceland', 'russian': 'Russia',
        'ukrainian': 'Ukraine', 'polish': 'Poland',
        'czech': 'Czech Republic', 'slovak': 'Slovakia',
        'hungarian': 'Hungary', 'romanian': 'Romania',
        'bulgarian': 'Bulgaria', 'serbian': 'Serbia',
        'croatian': 'Croatia', 'slovenian': 'Slovenia',
        'bosnian': 'Bosnia and Herzegovina', 'albanian': 'Albania',
        'greek': 'Greece', 'turkish': 'Turkey',
        'estonian': 'Estonia', 'latvian': 'Latvia',
        'lithuanian': 'Lithuania', 'maltese': 'Malta',

        # Asian Languages
        'mandarin': 'China', 'cantonese': 'China',
        'japanese': 'Japan', 'korean': 'South Korea',
        'vietnamese': 'Vietnam', 'thai': 'Thailand',
        'hindi': 'India', 'bengali': 'Bangladesh',
        'punjabi': 'India', 'tamil': 'India',
        'telugu': 'India', 'urdu': 'Pakistan',
        'indonesian': 'Indonesia', 'malay': 'Malaysia',
        'filipino': 'Philippines', 'burmese': 'Myanmar',
        'khmer': 'Cambodia', 'lao': 'Laos',
        'mongolian': 'Mongolia', 'nepali': 'Nepal',
        'sinhala': 'Sri Lanka', 'dzongkha': 'Bhutan',

        # Middle Eastern Languages
        'arabic': 'Egypt', 'egyptian arabic': 'Egypt',
        'saudi arabic': 'Saudi Arabia', 'hebrew': 'Israel',
        'persian': 'Iran', 'pashto': 'Afghanistan',
        'dari': 'Afghanistan', 'kurdish': 'Iraq',
        'turkmen': 'Turkmenistan', 'uzbek': 'Uzbekistan',
        'kazakh': 'Kazakhstan',

        # African Languages
        'swahili': 'Tanzania', 'amharic': 'Ethiopia',
        'yoruba': 'Nigeria', 'hausa': 'Nigeria',
        'igbo': 'Nigeria', 'somali': 'Somalia',
        'afrikaans': 'South Africa', 'zulu': 'South Africa',
        'xhosa': 'South Africa', 'shona': 'Zimbabwe',
        'malagasy': 'Madagascar',

        # Americas
        'american english': 'United States',
        'canadian english': 'Canada',
        'mexican spanish': 'Mexico',
        'argentine spanish': 'Argentina',
        'brazilian portuguese': 'Brazil',
        'quebec french': 'Canada',
        'haitian creole': 'Haiti',
        'jamaican patois': 'Jamaica',

        # Other
        'esperanto': 'International',
        'latin': 'Vatican City'
    }

    # Country code top-level domains
    COUNTRY_TLDS = {
        # ====== OFFICIAL COUNTRY CODE TLDs ======
        # Europe
        '.al': 'Albania', '.ad': 'Andorra', '.am': 'Armenia', '.at': 'Austria',
        '.az': 'Azerbaijan', '.by': 'Belarus', '.be': 'Belgium', '.ba': 'Bosnia and Herzegovina',
        '.bg': 'Bulgaria', '.hr': 'Croatia', '.cy': 'Cyprus', '.cz': 'Czech Republic',
        '.dk': 'Denmark', '.ee': 'Estonia', '.fi': 'Finland', '.fr': 'France',
        '.ge': 'Georgia', '.de': 'Germany', '.gr': 'Greece', '.hu': 'Hungary',
        '.is': 'Iceland', '.ie': 'Ireland', '.it': 'Italy', '.kz': 'Kazakhstan',
        '.lv': 'Latvia', '.li': 'Liechtenstein', '.lt': 'Lithuania', '.lu': 'Luxembourg',
        '.mk': 'North Macedonia', '.mt': 'Malta', '.md': 'Moldova', '.mc': 'Monaco',
        '.me': 'Montenegro', '.nl': 'Netherlands', '.no': 'Norway', '.pl': 'Poland',
        '.pt': 'Portugal', '.ro': 'Romania', '.ru': 'Russia', '.sm': 'San Marino',
        '.rs': 'Serbia', '.sk': 'Slovakia', '.si': 'Slovenia', '.es': 'Spain',
        '.se': 'Sweden', '.ch': 'Switzerland', '.tr': 'Turkey', '.ua': 'Ukraine',
        '.uk': 'United Kingdom', '.va': 'Vatican City',
       
        # Americas
        '.ai': 'Anguilla', '.ag': 'Antigua and Barbuda', '.ar': 'Argentina', '.aw': 'Aruba',
        '.bs': 'Bahamas', '.bb': 'Barbados', '.bz': 'Belize', '.bm': 'Bermuda',
        '.bo': 'Bolivia', '.br': 'Brazil', '.vg': 'British Virgin Islands', '.ca': 'Canada',
        '.ky': 'Cayman Islands', '.cl': 'Chile', '.co': 'Colombia', '.cr': 'Costa Rica',
        '.cu': 'Cuba', '.dm': 'Dominica', '.do': 'Dominican Republic', '.ec': 'Ecuador',
        '.sv': 'El Salvador', '.fk': 'Falkland Islands', '.gd': 'Grenada', '.gt': 'Guatemala',
        '.gy': 'Guyana', '.ht': 'Haiti', '.hn': 'Honduras', '.jm': 'Jamaica',
        '.mx': 'Mexico', '.ni': 'Nicaragua', '.pa': 'Panama', '.py': 'Paraguay',
        '.pe': 'Peru', '.pr': 'Puerto Rico', '.bl': 'Saint Barthélemy', '.kn': 'Saint Kitts and Nevis',
        '.lc': 'Saint Lucia', '.mf': 'Saint Martin', '.vc': 'Saint Vincent and the Grenadines',
        '.sr': 'Suriname', '.tt': 'Trinidad and Tobago', '.tc': 'Turks and Caicos Islands',
        '.us': 'United States', '.uy': 'Uruguay', '.ve': 'Venezuela',
        
        # Asia
        '.af': 'Afghanistan', '.bh': 'Bahrain', '.bd': 'Bangladesh', '.bt': 'Bhutan',
        '.bn': 'Brunei', '.kh': 'Cambodia', '.cn': 'China', '.tw': 'Taiwan',
        '.in': 'India', '.id': 'Indonesia', '.ir': 'Iran', '.iq': 'Iraq',
        '.il': 'Israel', '.jp': 'Japan', '.jo': 'Jordan', '.kw': 'Kuwait',
        '.kg': 'Kyrgyzstan', '.la': 'Laos', '.lb': 'Lebanon', '.mo': 'Macao',
        '.my': 'Malaysia', '.mv': 'Maldives', '.mn': 'Mongolia', '.mm': 'Myanmar',
        '.np': 'Nepal', '.kp': 'North Korea', '.om': 'Oman', '.pk': 'Pakistan',
        '.ps': 'Palestine', '.ph': 'Philippines', '.qa': 'Qatar', '.sa': 'Saudi Arabia',
        '.sg': 'Singapore', '.kr': 'South Korea', '.lk': 'Sri Lanka', '.sy': 'Syria',
        '.tj': 'Tajikistan', '.th': 'Thailand', '.tl': 'Timor-Leste', '.ae': 'United Arab Emirates',
        '.uz': 'Uzbekistan', '.vn': 'Vietnam', '.ye': 'Yemen',

        # Africa
        '.dz': 'Algeria', '.ao': 'Angola', '.bj': 'Benin', '.bw': 'Botswana',
        '.bf': 'Burkina Faso', '.bi': 'Burundi', '.cv': 'Cape Verde', '.cm': 'Cameroon',
        '.cf': 'Central African Republic', '.td': 'Chad', '.km': 'Comoros', '.cd': 'Congo (Kinshasa)',
        '.cg': 'Congo (Brazzaville)', '.ci': "Côte d'Ivoire", '.dj': 'Djibouti', '.eg': 'Egypt',
        '.gq': 'Equatorial Guinea', '.er': 'Eritrea', '.sz': 'Eswatini', '.et': 'Ethiopia',
        '.ga': 'Gabon', '.gm': 'Gambia', '.gh': 'Ghana', '.gn': 'Guinea',
        '.gw': 'Guinea-Bissau', '.ke': 'Kenya', '.ls': 'Lesotho', '.lr': 'Liberia',
        '.ly': 'Libya', '.mg': 'Madagascar', '.mw': 'Malawi', '.ml': 'Mali',
        '.mr': 'Mauritania', '.mu': 'Mauritius', '.yt': 'Mayotte', '.ma': 'Morocco',
        '.mz': 'Mozambique', '.na': 'Namibia', '.ne': 'Niger', '.ng': 'Nigeria',
        '.re': 'Réunion', '.rw': 'Rwanda', '.sh': 'Saint Helena', '.st': 'Sao Tome and Principe',
        '.sn': 'Senegal', '.sc': 'Seychelles', '.sl': 'Sierra Leone', '.so': 'Somalia',
        '.za': 'South Africa', '.ss': 'South Sudan', '.sd': 'Sudan', '.tz': 'Tanzania',
        '.tg': 'Togo', '.tn': 'Tunisia', '.ug': 'Uganda', '.eh': 'Western Sahara',
        '.zm': 'Zambia', '.zw': 'Zimbabwe',

       # Oceania
        '.as': 'American Samoa', '.au': 'Australia', '.ck': 'Cook Islands', '.fj': 'Fiji',
        '.pf': 'French Polynesia', '.gu': 'Guam', '.ki': 'Kiribati', '.mh': 'Marshall Islands',
        '.fm': 'Micronesia', '.nr': 'Nauru', '.nc': 'New Caledonia', '.nz': 'New Zealand',
        '.nu': 'Niue', '.nf': 'Norfolk Island', '.mp': 'Northern Mariana Islands', '.pw': 'Palau',
        '.pg': 'Papua New Guinea', '.pn': 'Pitcairn', '.ws': 'Samoa', '.sb': 'Solomon Islands',
        '.tk': 'Tokelau', '.to': 'Tonga', '.tv': 'Tuvalu', '.vu': 'Vanuatu',

        # ====== SPECIAL CASES & SECOND-LEVEL DOMAINS ======
        # UK second-level domains
        '.ac.uk': 'United Kingdom', '.gov.uk': 'United Kingdom', '.co.uk': 'United Kingdom',
        '.org.uk': 'United Kingdom', '.me.uk': 'United Kingdom', '.net.uk': 'United Kingdom',
            
        # Australia second-level
        '.com.au': 'Australia', '.org.au': 'Australia', '.net.au': 'Australia',
        '.gov.au': 'Australia', '.edu.au': 'Australia',
            
        # Other notable second-levels
       '.edu': 'United States', '.gov': 'United States', '.mil': 'United States',
       '.gc.ca': 'Canada', '.gob.mx': 'Mexico', '.gov.in': 'India',
            
     # Generic TLDs with geographic significance
     '.asia': 'Asia', '.eu': 'European Union', '.lat': 'Latin America'
    }

    def __init__(self):
        self.classifier = TranslationClassifier()
        try:
            model_path = os.path.abspath('lid.176.ftz')
            if os.path.exists(model_path):
                self.FASTTEXT_MODEL = fasttext.load_model(model_path)
            else:
                self.FASTTEXT_MODEL = None
                logging.warning("FastText model not found, using fallback methods")
        except Exception as e:
            logging.warning(f"Fasttext model error: {str(e)}")
            self.FASTTEXT_MODEL = None
            
        # Initialize Excel workbook
        self.wb = Workbook()
        self.ws = self.wb.active
        self.ws.title = "News Items"
        
        # Add headers
        headers = [
            'Article URL',
            'Date',
            'Document_Type',
            'Product_Type',
            'Countries',
            'Regions',
            'Drug_names',
            'Language',
            'Source URL',
            'Title',
            'Summary'
        ]
        
        self.ws.append(headers)
        # Make headers bold
        for cell in self.ws[1]:
            cell.font = Font(bold=True)
              
        super().__init__()
    
    def detect_language(self, text: str) -> str:
        """Detect language of given text with improved error handling"""
        if not text or len(text.strip()) < 3:
            return "Unknown"
        # First try with fasttext if available
        if self.FASTTEXT_MODEL:
            try:
                text_for_pred = text.replace("\n", " ").strip()
                if not text_for_pred:
                    return "Unknown"
                
                prediction = self.FASTTEXT_MODEL.predict(text_for_pred)
                lang_code = prediction[0][0].replace('__label__', '')
                try:
                    return Lang(alpha2=lang_code).name.lower()
                except:
                    pass  # Fall through to other methods
            except Exception as e:
                logging.debug(f"FastText prediction failed: {str(e)}")
                
        # Explicit check for Danish
        if any(danish_word in text.lower() for danish_word in ['af', 'og', 'i', 'for', 'er', 'som']):
            return 'danish'
        
        # Fallback to langdetect with longer text requirement
        if len(text) > 20:
            try:
                lang_code = detect(text)
                return Lang(alpha2=lang_code).name.lower()
            except:
                return "Unknown"
            
        return "Unknown"
        
    def safe_translate(self, text: str, src_lang: str) -> str:
        if not text:
            return text
        
        # Rate limiting
        time.sleep(random.uniform(1.0, 2.0))  # Increased delay
        
        try:
            # Split long texts into chunks
            if len(text) > 500:
                chunks = [text[i:i+400] for i in range(0, len(text), 400)]
                translated_chunks = []
                for chunk in chunks:
                    translated = self._translate_chunk(chunk, src_lang)
                    if translated:
                        translated_chunks.append(translated)
                    time.sleep(random.uniform(0.5, 1.5))
                return ' '.join(translated_chunks)
            else:
                return self._translate_chunk(text, src_lang)
        except Exception as e:
            self.logger.warning(f"Translation failed: {str(e)}")
            return text
        
    def _translate_chunk(self, text: str, src_lang: str) -> str:
        """Helper method to translate a single chunk with retries"""
        max_retries = 3
        for attempt in range(max_retries):
            try:
                if src_lang.lower() == 'danish':
                    return GoogleTranslator(source='da', target='en').translate(text)
                else:
                    lang_code = Lang(name=src_lang).part1
                    if lang_code:
                        return GoogleTranslator(source=lang_code, target='en').translate(text)
                    return text
            except Exception as e:
                if attempt == max_retries - 1:
                    raise
                time.sleep(2 ** attempt)  # Exponential backoff

    def detect_countries(self, text: str) -> Dict[str, List[str]]:
        """Detect countries and regions mentioned in text"""
        if not text:
            return {
                'mentioned_countries': [],
                'mentioned_regions': []
            }
            
        text_lower = text.lower()
        mentioned_countries = []
        mentioned_regions = set()
        
        # First check for exact country matches
        for country, patterns in self.COUNTRY_PATTERNS.items():
            for pattern in patterns:
                if re.search(rf'\b{re.escape(pattern)}\b', text_lower):
                    mentioned_countries.append(country)
                    # Add corresponding region if country is found
                    if country in self.REGION_MAPPING:
                        mentioned_regions.add(self.REGION_MAPPING[country])
                        break  # No need to check other patterns for this country
                    
        # Special handling for EU/EEA mentions
        eu_terms = ['eu', 'european union', 'eea', 'european economic area']
        if any(re.search(rf'\b{term}\b', text_lower) for term in eu_terms):
            mentioned_regions.add('European Union')
            if 'European Union' not in mentioned_countries:
                mentioned_countries.append('European Union')
                
        # Remove duplicates while preserving order
        seen = set()
        unique_countries = [c for c in mentioned_countries if not (c in seen or seen.add(c))]
        
        return {
            'mentioned_countries': unique_countries,
            'mentioned_regions': list(mentioned_regions)
        }

    def infer_country(self, url: str, language: str) -> str:
        """Infer country based on URL TLD and language"""
        for tld, country in self.COUNTRY_TLDS.items():
            if tld in url.lower():
                return country
        
        if language in self.LANGUAGE_TO_COUNTRY:
            return self.LANGUAGE_TO_COUNTRY[language]
        
        return "Unknown"

    def parse(self, response):
        items = response.css('div.itemtext')
        
        if not items:
            self.logger.warning(f"No items found on page: {response.url}")
            return
        
        for item in items:
            # Extract all text elements properly
            all_texts = item.css('span.ellipsis_text::text').getall()
        
            # Initialize lists for titles and content
            titles = []
            contents = []
        
            # Process each text element
            for text in all_texts:
                if text and isinstance(text, str):  # Check if text exists and is string
                    if text.startswith('\r\n'):  # Title has leading \r\n and spaces
                        titles.append(text.strip())
                    else:
                        contents.append(text.strip())
        
            # Get the first title and content if available
            title = titles[0] if titles else None
            content = ' '.join(contents) if contents else None
        
            # Date processing
            raw_date = item.css('span.date::text').get(default="").strip()
            numeric_date = None
            
            if raw_date:
                try:
                    date_obj = dateparser.parse(raw_date, languages=['da'])  # 'da' for Danish
                    
                    if date_obj:
                        numeric_date = date_obj.strftime('%d-%m-%Y')
                        
                    else:
                        raise ValueError("Could not parse date")
                except Exception as e:
                    self.logger.warning(f"Failed to parse date '{raw_date}': {e}")
                    numeric_date = raw_date
        
            # Get URL
            url = response.urljoin(item.css('a::attr(href)').get())
        
            # Skip if essential data is missing
            if not title or not content:
                self.logger.debug(f"Skipping item with missing data: {url}")
                continue
            
            try:
                # Language detection
                lang = self.detect_language(f"{title} {content}")
                 
                # First translate everything to English
                title_en = self.safe_translate(title, lang)
                content_en = self.safe_translate(content, lang)
                combined_en = f"{title_en} {content_en}"

                # Now perform classifications
                doc_info = self.classifier.classify_document(combined_en)
                product_info = self.classifier.classify_product(combined_en)                 
                
                # NEW - Drug extraction from three sources
                content_drugs = self.classifier.extract_drug_names(content_en)
                title_drugs = self.classifier.extract_drug_names(title_en)
                product_info_text = product_info.get('product_keywords', '') + " " + product_info.get('product_type', '')
                product_drugs = self.classifier.extract_drug_names(product_info_text)
                drug_names_final = list(set(content_drugs + title_drugs + product_drugs))
                drug_names_str = ', '.join(drug_names_final) if drug_names_final else "None"

                
                # Country detection also on English text
                country_info = self.detect_countries(combined_en)
                inferred_country = self.infer_country(url, lang)
                
                # Convert lists to comma-separated strings
                mentioned_countries = country_info.get('mentioned_countries', [])
                mentioned_countries_str = ', '.join(mentioned_countries) if isinstance(mentioned_countries, (list, tuple)) else ''
                mentioned_regions = country_info.get('mentioned_regions', [])
                mentioned_regions_str = ', '.join(mentioned_regions) if isinstance(mentioned_regions, (list, tuple)) else ''
                doc_keywords = doc_info.get('matched_keywords', [])
                doc_keywords_str = ', '.join(doc_keywords) if isinstance(doc_keywords, (list, tuple)) else ''
                product_keywords = product_info.get('product_keywords', [])
                product_keywords_str = ', '.join(product_keywords) if isinstance(product_keywords, (list, tuple)) else ''
                
                row = [
                    url,
                    numeric_date,
                    doc_info.get('document_type') or "None",
                    product_info.get('product_type') or "None",
                    mentioned_countries_str if mentioned_countries_str else "None",
                    mentioned_regions_str if mentioned_regions_str else "None",
                    drug_names_str,
                    lang,
                    'https://laegemiddelstyrelsen.dk/da/nyheder/',
                    title_en if title_en else "None",
                    content_en if content_en else "None"
                ]

                
                self.ws.append(row)
                
            except Exception as e:
                self.logger.error(f"Error processing item: {str(e)}", exc_info=True)
                continue

        # Pagination
        next_page_link = response.css('a.next-arrow[href]')
        if next_page_link and self.current_page < self.max_pages:
            next_page_url = next_page_link.attrib['href']
            self.current_page += 1  # Increment the page counter
            self.logger.debug(f"Found next page link, moving from page {self.current_page-1} to {self.current_page}")
            yield response.follow(next_page_url, callback=self.parse)
        else:
            self.logger.info(f"Reached maximum page limit ({self.max_pages}) or no more pages found, stopping pagination")

    @classmethod
    def from_crawler(cls, crawler, *args, **kwargs):
        spider = super(DK1Spider, cls).from_crawler(crawler, *args, **kwargs)
        crawler.signals.connect(spider.spider_closed, signal=signals.spider_closed)
        return spider
    
    def spider_closed(self, spider):
        # Save the workbook when spider closes
        output_path = os.path.join(os.getcwd(), 'DKnews_items.xlsx')
        self.wb.save(output_path)
        logging.info(f"Excel file saved to {output_path}")

if __name__ == "__main__":
    from scrapy.crawler import CrawlerProcess

    process = CrawlerProcess()
    process.crawl(DK1Spider)
    process.start()
