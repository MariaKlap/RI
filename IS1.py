import scrapy
from langdetect import detect, LangDetectException
from datetime import datetime
from typing import Dict, List, Optional
import re
from urllib.parse import urljoin
import pandas as pd
from deep_translator import GoogleTranslator
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from scrapy.selector import Selector
import time
import re
from openpyxl import Workbook
from openpyxl.styles import Font
import pandas as pd
from scrapy.crawler import CrawlerProcess


class ISnewsSpider(scrapy.Spider):
    name = 'IS1'
    start_urls = ['https://www.ima.is/frettir/']
    max_pages = 3
    current_page = 1
    
    custom_settings = {
        'USER_AGENT': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'DOWNLOAD_DELAY': 2,
        'CONCURRENT_REQUESTS': 1,
        'AUTOTHROTTLE_ENABLED': True,
        'AUTOTHROTTLE_START_DELAY': 5,
        'HTTPCACHE_ENABLED': True
    }
        
    def __init__(self, max_pages=3, *args, **kwargs):
        self.data_rows = []
        super().__init__(*args, **kwargs)
        
        
        self.max_pages = int(max_pages)

        self.wb = Workbook()
        self.ws = self.wb.active
        self.ws.title = "IS News"

        headers = [
            'Title', 'Summary', 'Article URL', 'Date', 'Document_Type',
            'Product_Type', 'Countries', 'Regions', 'Drug_names',
            'Language', 'Source URL'
        ]

        self.ws.append(headers)

        for cell in self.ws[1]:
            cell.font = Font(bold=True)

        self.row_count = 2

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

    
    def detect_language(self, text: str) -> str:
        """Detect language and return the full language name"""
        if not text.strip():
            return "Unknown"
        try:
            lang_code = detect(text)
            return self.LANGUAGE_NAMES.get(lang_code, f"Unknown ({lang_code})")
        except LangDetectException:
            return "Unknown"


    def start_requests(self):
        options = webdriver.ChromeOptions()
        options.add_argument('--headless')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        
        self.driver = webdriver.Chrome(options=options)
        try:
            self.driver.get(self.start_urls[0])
            
            while self.current_page <= self.max_pages:
                # Wait for news items to load
                try:
                    WebDriverWait(self.driver, 15).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, ".articlelist__item"))
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
                    # Look for pagination links - adjust selector based on actual site structure
                    next_page_links = self.driver.find_elements(By.CSS_SELECTOR, "a.page-link:contains('Next'), a:contains('>')")
                    
                    if not next_page_links:
                        self.logger.info(f"No more pages found. Current page: {self.current_page}")
                        break
                        
                    next_page_link = next_page_links[0]
                    
                    # Scroll to and click the element
                    self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", next_page_link)
                    time.sleep(0.5)  # Small pause for scroll to complete
                    
                    # Save current URL to detect page change
                    current_url = self.driver.current_url
                    
                    self.driver.execute_script("arguments[0].click();", next_page_link)
                    
                    # Wait for either URL to change or new content to load
                    WebDriverWait(self.driver, 15).until(
                        lambda driver: driver.current_url != current_url or
                        len(driver.find_elements(By.CSS_SELECTOR, f".articlelist__item[data-page='{next_page_num}']")) > 0
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
        try:
            articles = sel.xpath('//div[@class="articlelist__item"]')
            
            for article in articles:
                item = {}
                # Extract date
                date_str = article.xpath('.//time/text()').get()
                item['Date'] = self.format_date(date_str) if date_str else "Unknown"
                
                # Extract title and URL
                title_elem = article.xpath('.//h3/a')
                item['Title'] = title_elem.xpath('text()').get()
                Article_URL = title_elem.xpath('@href').get()
                
                # Get the base URL from your start_urls
                base_url = self.start_urls[0]
                item['Article URL'] = urljoin(base_url, Article_URL) if Article_URL else None
                
                # Extract summary
                item['Summary'] = ' '.join(article.xpath('.//div[@class="articlelist__item__summary"]//text()').getall()).strip()
                
                if item['Article URL']:
                    yield scrapy.Request(
                        item['Article URL'],
                        callback=self.parse_detail_page,
                        meta={'item': item}
                        )
                    
        except Exception as e:
            # Log the error with the current URL being processed
            current_url = getattr(self, 'current_url', 'unknown URL')
            self.logger.error(f"Error parsing page {current_url}: {str(e)}")
            return

    def extract_drug_names(self, text: str) -> List[str]:
        if not text.strip():
            return []

        matched = []
        for term in self.drug_terms_set:
            # Escape regex special chars and match as whole word/phrase
            pattern = r'(?<!\w)' + re.escape(term) + r'(?!\w)'
            if re.search(pattern, text, flags=re.IGNORECASE):
                matched.append(term)
        return matched

    def parse_detail_page(self, response):
        item = response.meta['item']
        
        # Improved content extraction with multiple selector options
        content_selectors = [
            '.article-content', 
            '.article-body', 
            '.content-area',
            'div.mod-article'
        ]
        
        full_text = ''
        for selector in content_selectors:
            if response.css(selector):
                full_text = ' '.join(response.css(selector + ' ::text').getall()).strip()
                if full_text:
                    break
        
        # Fallback to all paragraph text if specific selectors fail
        if not full_text:
            full_text = ' '.join(response.css('p::text').getall()).strip()
        
        # Clean text
        full_text = ' '.join(full_text.split())
        
        # Translate if not English
        lang = self.detect_language(full_text)
        lang_code = detect(full_text) if lang != "Unknown" else None

        if lang != "English":
            try:
                translated_text = GoogleTranslator(
                    source=lang_code if lang_code else 'auto',
                    target='en'
                ).translate(full_text[:5000])
            except Exception as e:
                self.logger.error(f"Translation failed: {str(e)}")
                translated_text = full_text
        else:
            translated_text = full_text


        # Generate summary early so we can use it below
        summary_text = self.generate_summary(translated_text) if translated_text else "No text content available"
        item['Summary'] = summary_text

        # Now it's safe to build the full text to search
        combined_text = f"{translated_text} {item['Title']} {summary_text}"
        drug_names = self.extract_drug_names(combined_text)
        item['Drug_names'] = ", ".join(drug_names) if drug_names else "None"

        # Process item fields
        item['Source URL'] = self.start_urls[0]
        item['Title'] = item['Title']  # Keep original title for now
        item['Date'] = item.get('Date', "Unknown")
        item['Summary'] = self.generate_summary(translated_text) if translated_text else "No text content available"
        item['Product_Type'] = self.classify_product_type(translated_text)
        item['Document_Type'] = self.classify_document_type(translated_text)
        item['Article URL'] = response.url
        item['Language'] = lang

        # Detect countries and regions from the translated text
        mentioned_countries = self.detect_mentioned_countries(translated_text)
        mentioned_regions = self.detect_mentioned_regions(mentioned_countries)

        item['Countries'] = ", ".join(mentioned_countries) if mentioned_countries else "None"
        item['Regions'] = ", ".join(mentioned_regions) if mentioned_regions else "None"

        # Append to dataset
        self.data_rows.append({
            'Title': item['Title'],
            'Summary': item['Summary'],
            'Article URL': item['Article URL'],
            'Date': item['Date'],
            'Document_Type': item['Document_Type'],
            'Product_Type': item['Product_Type'],
            'Countries': item['Countries'],
            'Regions': item['Regions'],
            'Drug_names': item['Drug_names'],
            'Language': item['Language'],
            'Source URL': item['Source URL']
        })

        
        yield item

    def parse(self, response):
        if response.status != 200:
            self.logger.error(f"Failed to fetch page: {response.url}")
            return

        try:
            articles = response.css('.articlelist__item')
            
            for article in articles:
                item = {}
                # Extract date
                date_str = article.css('time::text').get()
                item['Date'] = self.format_date(date_str) if date_str else "Unknown"
                
                # Extract title and URL
                title_elem = article.css('h3 a')
                item['Title'] = title_elem.css('::text').get()
                Article_URL = title_elem.attrib.get('href')
                item['Article URL'] = urljoin(response.url, Article_URL) if Article_URL else None
                
                # Extract summary
                item['Summary'] = ' '.join(article.css('.articlelist__item__summary ::text').getall()).strip()
                
                if item['Article URL']:
                    yield scrapy.Request(
                        item['Article URL'],
                        callback=self.parse_detail_page,
                        meta={'item': item}
                    )
                    
        except Exception as e:
            self.logger.error(f"Error parsing page {response.url}: {str(e)}")
            return
        
    def generate_summary(self, text, max_length=300, min_length=30):
        if not text.strip():
            return "No text available"
        
        # Clean and truncate text
        clean_text = ' '.join(text.split()[:1500])
        
        # If text is very short, return it directly
        if len(clean_text.split()) < min_length:
            return clean_text[:max_length] + "..."
        
        # Fallback summary: return first few meaningful sentences
        sentences = [s.strip() for s in re.split(r'[.!?]', clean_text) if len(s.split()) > 5]
        if sentences:
            return ' '.join(sentences[:3])[:max_length] + '...'
        
        # If no sentences found, fallback to truncate
        return clean_text[:max_length] + "..."


    def translate_to_english(self, text: str) -> str:
        """Improved translation with Icelandic support"""
        if not text.strip():
            return text
            
        lang = self.detect_language(text)
        if lang == "English":
            return text

        try:
            return GoogleTranslator(
                source='is' if lang == "Icelandic" else 'auto',
                target='en'
            ).translate(text[:5000])  # Limit translation length
        except Exception as e:
            self.logger.error(f"Translation failed: {str(e)}")
            return text

            
    def format_date(self, date_str):
        """Handle Icelandic date formats"""
        if not date_str or not date_str.strip():
            return "Unknown"
        
        try:
            # Handle Icelandic date format (dd.mm.yyyy)
            if '.' in date_str:
                day, month, year = date_str.split('.')
                return f"{day.zfill(2)}/{month.zfill(2)}/{year}"
            
            # Try other formats
            for fmt in ("%d-%m-%Y", "%Y-%m-%d", "%B %d, %Y"):
                try:
                    date_obj = datetime.strptime(date_str, fmt)
                    return date_obj.strftime("%d/%m/%Y")
                except ValueError:
                    continue
        except Exception as e:
            self.logger.error(f"Date formatting error for '{date_str}': {str(e)}")
        
        return date_str
          
    
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
        df = pd.DataFrame(self.data_rows)
        df['Date'] = pd.to_datetime(df['Date'], dayfirst=True, errors='coerce')

        df = df.dropna(subset=['Date']).sort_values(by='Date', ascending=False)

        # Keep only top 15 newest news
        df = df.head(15)
        df['Date'] = df['Date'].dt.strftime('%d-%m-%Y')

        df.to_excel("IS_news.xlsx", index=False)
        
        # Clean up resources
        if hasattr(self, 'summarizer'):
            del self.summarizer
        if hasattr(self, 'nlp_is'):
            del self.nlp_is
        if hasattr(self, 'nlp_en'):
            del self.nlp_en

if __name__ == "__main__":
    process = CrawlerProcess()
    process.crawl(ISnewsSpider)
    process.start()

