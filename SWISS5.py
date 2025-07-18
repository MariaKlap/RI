import scrapy
from langdetect import detect, LangDetectException
import os
from datetime import datetime
from typing import Dict, List
import re
from urllib.parse import urljoin
from openpyxl import Workbook
from openpyxl.styles import Font
from scrapy import Spider, Selector, Request
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
import time
import pandas as pd


class SWISSnewsSpider(scrapy.Spider):
    name = 'SWISS5'
    start_urls = ['https://www.swissmedic.ch/swissmedic/en/home/news/updates.html']
    max_pages = 5  # Set maximum pages to scrape
    current_page = 1  # Track current page
    
    custom_settings = {
        'USER_AGENT': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'DUPEFILTER_DEBUG': True,
        'DUPEFILTER_CLASS': 'scrapy.dupefilters.BaseDupeFilter',
        'DOWNLOAD_DELAY': 2,
        'HTTPCACHE_DIR': 'httpcache',
        'HTTPCACHE_POLICY': 'scrapy.extensions.httpcache.RFC2616Policy',
        'HTTPCACHE_STORAGE': 'scrapy.extensions.httpcache.FilesystemCacheStorage',
        'HTTPCACHE_ENABLED': False,
        'CONCURRENT_REQUESTS': 1,
        'AUTOTHROTTLE_ENABLED': True,
        'AUTOTHROTTLE_START_DELAY': 5,
        'AUTOTHROTTLE_MAX_DELAY': 60,
        'AUTOTHROTTLE_TARGET_CONCURRENCY': 0.5
    }
        
    def __init__(self, max_pages=3, *args, **kwargs):
        super().__init__(*args, **kwargs)
        super(SWISSnewsSpider, self).__init__(*args, **kwargs)
        self.max_pages = max_pages
        self.current_page = 1
        self.seen_urls = set() 
        
        # Load drug names from the TSV file
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
        
        # Initialize Excel workbook
        self.wb = Workbook()
        self.ws = self.wb.active
        self.ws.title = "SWISS News"
        
        # Write headers
        headers = [
            'Title', 'Summary', 'Article URL', 'Date', 'Document_Type', 
            'Product_Type', 'Countries', 'Regions', 'Drug_names', 
            'Language', 'Source URL'
            ]
        
        self.ws.append(headers)
        
        # Make headers bold
        for cell in self.ws[1]:
            cell.font = Font(bold=True)
        
        self.row_count = 2
        
        # Language code to full name mapping
        self.LANGUAGE_NAMES = {
            'af': 'Afrikaans',
            'ar': 'Arabic',
            'bg': 'Bulgarian',
            'bn': 'Bengali',
            'ca': 'Catalan',
            'cs': 'Czech',
            'cy': 'Welsh',
            'da': 'Danish',
            'de': 'German',
            'el': 'Greek',
            'en': 'English',
            'es': 'Spanish',
            'et': 'Estonian',
            'fa': 'Persian',
            'fi': 'Finnish',
            'fr': 'French',
            'gu': 'Gujarati',
            'he': 'Hebrew',
            'hi': 'Hindi',
            'hr': 'Croatian',
            'hu': 'Hungarian',
            'id': 'Indonesian',
            'it': 'Italian',
            'ja': 'Japanese',
            'kn': 'Kannada',
            'ko': 'Korean',
            'lt': 'Lithuanian',
            'lv': 'Latvian',
            'mk': 'Macedonian',
            'ml': 'Malayalam',
            'mr': 'Marathi',
            'ne': 'Nepali',
            'nl': 'Dutch',
            'no': 'Norwegian',
            'pa': 'Punjabi',
            'pl': 'Polish',
            'pt': 'Portuguese',
            'ro': 'Romanian',
            'ru': 'Russian',
            'sk': 'Slovak',
            'sl': 'Slovenian',
            'so': 'Somali',
            'sq': 'Albanian',
            'sv': 'Swedish',
            'sw': 'Swahili',
            'ta': 'Tamil',
            'te': 'Telugu',
            'th': 'Thai',
            'tl': 'Tagalog',
            'tr': 'Turkish',
            'uk': 'Ukrainian',
            'ur': 'Urdu',
            'vi': 'Vietnamese',
            'zh-cn': 'Chinese (Simplified)',
            'zh-tw': 'Chinese (Traditional)'
        }        
            
        # Document type classification
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

        # Product type classification
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

        # Country patterns for detection in text
        self.COUNTRY_PATTERNS = {
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
        self.REGION_MAPPING = {
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

    def start_requests(self):
        self.driver = webdriver.Chrome()
        try:
            self.driver.get(self.start_urls[0])
            
            while self.current_page <= self.max_pages:
                # Wait for news items to load
                try:
                    WebDriverWait(self.driver, 15).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, ".mod-teaser"))
                    )
                except TimeoutException:
                    self.logger.warning("Timed out waiting for news items")
                    break
                
                # Process current page
                sel = Selector(text=self.driver.page_source)
                yield from self.parse_selenium_page(sel)
                
                # Check if we've reached the last page
                if self.current_page >= self.max_pages:
                    break
                    
                # Try to find next page button
                next_page_num = self.current_page + 1
                try:
                    page_links = self.driver.find_elements(By.XPATH, 
                        f"//a[@data-loadpage='{next_page_num}']")
                    
                    if not page_links:
                        self.logger.info(f"No more pages found. Current page: {self.current_page}")
                        break
                        
                    page_link = page_links[0]
                    
                    # Scroll to and click the element
                    self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", page_link)
                    time.sleep(0.5)  # Small pause for scroll to complete
                    self.driver.execute_script("arguments[0].click();", page_link)
                    
                    # Wait for content to update
                    WebDriverWait(self.driver, 15).until(
                        lambda driver: len(driver.find_elements(
                            By.CSS_SELECTOR, f".mod-teaser[data-page='{next_page_num}']")) > 0 or
                        len(driver.find_elements(By.CSS_SELECTOR, ".mod-teaser")) > 0
                    )
                    
                    self.current_page += 1
                    time.sleep(1)  # Small delay for page to stabilize
                    
                except TimeoutException:
                    self.logger.warning(f"Timed out waiting for page {next_page_num} to load")
                    break
                except Exception as e:
                    self.logger.error(f"Pagination error: {str(e)}")
                    break
        finally:
            self.driver.quit()

    def parse_selenium_page(self, sel):
        """Parse a page loaded by Selenium"""
        articles = sel.css('.mod-teaser')

        for article in articles:
            relative_url = article.css('h3 a::attr(href)').get()
            full_url = urljoin(self.start_urls[0], relative_url)
            item = {
                'Title': article.css('h3 a::text').get(),
                'Article URL': full_url,
                'Date': article.css('.teaserDate::text').get(),
                'Description': article.css('.wrapper div::text').get().strip() if article.css('.wrapper div::text').get() else None
            }

            if full_url and full_url not in self.seen_urls:
                self.seen_urls.add(full_url)
                yield Request(
                    full_url,
                    callback=self.parse_detail_page,
                    meta={'item': item},
                    dont_filter=True
                )

                    
    def parse(self, response):
        self.logger.info(f"Processing page: {response.url}")
        
        if response.status != 200:
            self.logger.error(f"Failed to fetch page: {response.url}")
            return

        try:
            articles = response.xpath('//div[contains(@class, "mod-teaser")]')
            
            for article in articles:
                item = {}
                # Extract date
                date_str = article.xpath('.//p[@class="teaserDate"]/text()').get()
                item['Date'] = self.format_date(date_str) if date_str else "Unknown"
                
                # Extract title and URL
                title_elem = article.xpath('.//h3/a')
                item['Title'] = title_elem.xpath('@title').get() or title_elem.xpath('text()').get()
                item['Article URL'] = urljoin(response.url, title_elem.xpath('@href').get())
                
                if item['Article URL']:
                    yield scrapy.Request(
                        item['Article URL'],
                        callback=self.parse_detail_page,
                        meta={'item': item}
                    )

        except Exception as e:
            self.logger.error(f"Error parsing detail page {response.url}: {str(e)}")
            return
    
    def detect_language(self, text: str) -> str:
        """Detect language with caching and fallback logic"""
        if not text.strip():
            return "Unknown"
        
        # Simple English/German detection for Swiss context first
        if ' swissmedic ' in text.lower():
            return "German"
        try:
            lang_code = detect(text)
            return self.LANGUAGE_NAMES.get(lang_code, f"Unknown ({lang_code})")
        except LangDetectException:
            
            # Fallback to simple word checks
            german_words = ['der', 'die', 'das', 'und', 'für']
            english_words = ['the', 'and', 'for', 'of', 'in']
            german_count = sum(text.lower().count(word) for word in german_words)
            english_count = sum(text.lower().count(word) for word in english_words)
            return "German" if german_count > english_count else "English"

    def extract_drug_names(self, text: str, title: str = None) -> List[str]:
        if not text.strip():
            return []

        matched = []
        for term in self.drug_terms_set:
            # Escape regex special chars and match as whole word/phrase
            pattern = r'\b' + re.escape(term) + r'\b'
            if re.search(pattern, text, flags=re.IGNORECASE):
                matched.append(term)
        return matched
 


    def parse_detail_page(self, response):
        item = response.meta['item']
        
        item['url_hash'] = hash(response.url)
        
        main_content = response.css('.col-md-8 .mod.mod-text')
        if not main_content:
            # Fallback to .col-sm-8 if no content found
            main_content = response.css('.col-sm-8 .mod.mod-text')

        # Use only the first matched element
        main_content = main_content[0] if main_content else None
        
        
        # Extract title from h1 tag (more likely to be correct than h3 a)
        title = response.css('div.mod-html h1::text').get() or item['Title']
        
        # Extract all text content from the main content area
        full_text = ' '.join(main_content.xpath('.//text()[not(parent::script)]').getall()).strip()
        
        # Clean up the text by removing excessive whitespace
        full_text = ' '.join(full_text.split())
        
        # Translate the text to English before processing
        translated_text = self.translate_to_english(full_text)
        translated_title = self.translate_to_english(title)
        
        # Try to extract date from the text (if available)
        date = item['Date']  # Keep original date if no better one found
        
        # Process the item data using the translated text
        item['Title'] = translated_title if translated_title else title
        item['Date'] = date
        item['Summary'] = self.generate_summary(translated_text) if translated_text.strip() else "No text content available"
        item['Product_Type'] = self.classify_product_type(translated_text)
        item['Document_Type'] = self.classify_document_type(translated_text)
        
        # Extract other information from translated text
        mentioned_countries = self.detect_mentioned_countries(translated_text)
        item['Mentioned_Countries'] = ", ".join(mentioned_countries) if mentioned_countries else "None"
        item['Mentioned_Regions'] = ", ".join(self.detect_mentioned_regions(mentioned_countries)) if mentioned_countries else "None"
        item['Inferred_Country'] = "Switzerland"  # Since it's Swissmedic
        
        # Extract drug names - try title first, then fall back to text
        item['Drug_names'] = ", ".join(self.extract_drug_names(translated_text, translated_title)) or "None"
        
        # Detect language from original text (not translated)
        detected_language = self.detect_language(full_text)
        item['Language'] = detected_language if detected_language else "German"  # Fallback to German
        
        # Write to Excel
        row = [
            item['Title'],
            item['Summary'],
            item['Article URL'],
            item['Date'],
            item['Document_Type'],
            item['Product_Type'],
            item['Mentioned_Countries'],
            item['Mentioned_Regions'],
            item['Drug_names'],
            item['Language'],
            self.start_urls[0]  # Source URL
        ]
        
        self.ws.append(row)
        self.row_count += 1
        
        yield item
        
    def translate_to_english(self, text: str) -> str:
        """Dynamic translation that automatically handles any input length"""
        if not text.strip():
            return text
            
        try:
            # First detect language
            lang = self.detect_language(text)
            if "English" in lang:
                return text
                
            # Calculate dynamic max_length (input length + buffer)
            input_length = len(text)
            max_length = min(input_length + 500, 4096)  # 4096 is typical model max
            
            # Single translation attempt with dynamic length
            translated = self.translator(
                text,
                max_length=max_length,
                truncation=True  # Allow truncation if absolutely necessary
            )[0]['translation_text']
            return translated
            
        except Exception as e:
            self.logger.error(f"Translation failed: {str(e)}")
            return text  # Return original text if translation fails
            
    def format_date(self, date_str):
        """Convert date formats like '22.04.2025' to '22/04/2025'"""
        if not date_str or not date_str.strip():
            return "Unknown"
        
        try:
            # Handle Swiss/German date format (dd.mm.yyyy)
            if '.' in date_str:
                day, month, year = date_str.split('.')
                return f"{day.zfill(2)}/{month.zfill(2)}/{year}"
            
            # Try other formats if needed
            for fmt in ("%d-%m-%Y", "%Y-%m-%d", "%B %d, %Y"):
                try:
                    date_obj = datetime.strptime(date_str, fmt)
                    return date_obj.strftime("%d/%m/%Y")
                except ValueError:
                    continue
        except Exception as e:
            self.logger.error(f"Date formatting error for '{date_str}': {str(e)}")
        
        return date_str  # Return original if parsing fails       
    
    def generate_summary(self, text, max_length=60, min_length=40):
        if not text.strip():
            return "No text available"
        
        # Clean and truncate text to handle very long documents
        clean_text = ' '.join(text.split()[:1000])  # Reduced from 2000 to 1000 tokens
        
        if len(text.split()) < 50:
            return clean_text[:200] + "..."
        
        try: 
            summary = self.summarizer(
                clean_text, 
                max_length=max_length, 
                min_length=min_length, 
                do_sample=False,
                truncation=True
                )
            
            return summary[0]['summary_text']
        except Exception as e:
            self.logger.error(f"Summarization failed: {e}")
            
            # Fallback to first few sentences
            sentences = [s for s in re.split(r'[.!?]', text) if len(s.split()) > 5]
            return ' '.join(sentences[:3]) + '...'
    
    def classify_document_type(self, text: str) -> str:
        """Classify the document type based on text content."""
        text_lower = text.lower()
        for doc_type, keywords in self.DOCUMENT_TYPES.items():
            if any(keyword in text_lower for keyword in keywords):
                return doc_type
        return "Other Type"

    def classify_product_type(self, text: str) -> str:
        """Classify the product type based on text content."""
        text_lower = text.lower()
        for product_type, keywords in self.PRODUCT_TYPES.items():
            if any(keyword in text_lower for keyword in keywords):
                return product_type
        return "Other"

    def detect_mentioned_countries(self, text: str) -> List[str]:
        """More precise country detection with context awareness"""
        text_lower = text.lower()
        mentioned = []
        
        for country, patterns in self.COUNTRY_PATTERNS.items():
            # Skip African Union if text doesn't contain AU context
            if country == "African Union" and " au " not in text_lower:
                continue
            
            # Require at least 2 matches for international organizations
            if country in ("European Union", "African Union", "Global"):
                if sum(pattern in text_lower for pattern in patterns) >= 2:
                    mentioned.append(country)
                elif any(pattern in text_lower for pattern in patterns):
                    mentioned.append(country)
        return mentioned
    
    def detect_mentioned_regions(self, mentioned_countries):
        """Detect regions based on mentioned countries"""
        if not mentioned_countries:
            return []
        
        regions = set()
        for country in mentioned_countries:
            if country in self.REGION_MAPPING:
                regions.add(self.REGION_MAPPING[country])
                
        return list(regions)

    def infer_primary_country(self, mentioned_countries, text):
        if not mentioned_countries:
            return None
        from collections import Counter
        text_lower = text.lower()
        counts = Counter()
        for country in mentioned_countries:
            for pattern in self.COUNTRY_PATTERNS[country]:
                counts[country] += text_lower.count(pattern)
        return counts.most_common(1)[0][0] if counts else None
    
    def closed(self, reason):
        """Handle spider closing by saving Excel file and cleaning up resources"""
        try:
            # Save the Excel file in the current working directory
            output_path = "SWISS_news.xlsx"
            
            # Log the saving attempt (fixed syntax error here)
            self.logger.info(f"Attempting to save Excel file to: {os.path.abspath(output_path)}")
            self.logger.info(f"Workbook contains {self.row_count - 1} rows of data")
            
            # Save the workbook
            self.wb.save(output_path)
            self.logger.info("Excel file saved successfully")
            
        except Exception as e:
            # Log any errors that occur during saving
            self.logger.error(f"Failed to save Excel file: {str(e)}")
            self.logger.error("Traceback:", exc_info=True)
            
            # Attempt to save with a different name as fallback
            try:
                fallback_path = "SWISS_news_fallback.xlsx"
                self.wb.save(fallback_path)
                self.logger.warning(f"Saved to fallback location: {os.path.abspath(fallback_path)}")
            except Exception as fallback_e:
                self.logger.error(f"Fallback save also failed: {str(fallback_e)}")
                
        # Clean up resources
        if hasattr(self, 'summarizer'):
            del self.summarizer
        if hasattr(self, 'nlp'):
            del self.nlp
if __name__ == "__main__":
    process = CrawlerProcess()
    process.crawl(SWISSnewsSpider)
    process.start()

