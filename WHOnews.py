from selenium import webdriver
from deep_translator import GoogleTranslator
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.remote.webelement import WebElement
import re
import pandas as pd
from datetime import datetime
from urllib.parse import urljoin
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
import os
import time
import random
from typing import List, Dict, Optional
from selenium.common.exceptions import NoSuchElementException, StaleElementReferenceException, TimeoutException
import logging
from typing import List
from langdetect import detect, DetectorFactory
DetectorFactory.seed = 0

class WHOnews:
    def __init__(self, output_file='WHOnews.xlsx'):
        # Initialize logger
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.INFO)
        
        
        # Create console handler
        ch = logging.StreamHandler()
        ch.setLevel(logging.INFO)
        
        # Create formatter
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        ch.setFormatter(formatter)
        
        # Add handler to logger
        self.logger.addHandler(ch)

        self.output_file = output_file
        self.data_rows = []
        self.translator = GoogleTranslator(source='auto', target='en')
        
        self._init_country_mappings()

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


        # Chrome-specific configuration
        chrome_options = Options()
        prefs = {
            "profile.default_content_settings.popups": 0,
            "profile.content_settings.exceptions.automatic_downloads.*.setting": 1,
            "profile.default_content_setting_values.automatic_downloads": 1,
            "profile.default_content_setting_values.popups": 0
        }
        chrome_options.add_experimental_option("prefs", prefs)
        
        # Use ChromeDriverManager for automatic driver management
        service = Service(ChromeDriverManager().install())
        self.driver = webdriver.Chrome(service=service, options=chrome_options)

    def cleanup(self):
        """Clean up resources"""
        try:
            self.driver.quit()
        except Exception as e:
            print(f"⚠️ Error during cleanup: {e}")
    
    def _init_language_resources(self):
        """Initialize NLP resources on demand"""
        # Stanza for basic NLP
        try:
            stanza.download('en', processors='tokenize,ner')
            self.nlp = stanza.Pipeline('en', processors='tokenize,ner', use_gpu=False)
        except Exception as e:
            print(f"Failed to initialize Stanza: {e}")

        # Initialize country/region mappings
        self._init_country_mappings()

    def _init_country_mappings(self):
        """Initialize country and region mappings"""   
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
        
        # Product_Type classification
        self.PRODUCT_TYPES = {
        'Biological': [
            'biological', 'biologic', 'monoclonal antibody', 'mab', 'recombinant',
            'cell therapy', 'gene therapy', 'blood product', 'plasma derived'
        ],
        'Drug Product': [
            'drug product', 'finished product', 'formulation', 'dosage form',
            'tablet', 'capsule', 'injection', 'solution'
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

    def scrape_with_pagination(self, max_pages: int = 5) -> List[Dict]:
        """Scrape articles across multiple pages using pagination"""
        all_articles = []
        current_page = 1
        
        while current_page <= max_pages:
            try:
                self.logger.info(f"Scraping page {current_page}")
                
                # Scrape articles from current page
                page_articles = self._extract_article_metadata()
                all_articles.extend(page_articles)
                
                # Check if we should continue to next page
                if current_page >= max_pages:
                    break
                    
                # Find and click next page button
                next_page_button = self._find_next_page_button()
                if not next_page_button:
                    self.logger.info("No more pages available")
                    break
                    
                # Click the button and wait for page load
                next_page_button.click()
                time.sleep(2)  # Adjust based on your network speed
                
                # Wait for new content to load
                WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, ".link-container.table")))
                
                current_page += 1
                
            except Exception as e:
                self.logger.error(f"Error during pagination on page {current_page}: {str(e)}")
                break
                
        return all_articles

    def _find_next_page_button(self) -> Optional[WebElement]:
        """Find the next page button in the pagination controls"""
        try:
            # Look for the next page button with the specific class and aria-label
            next_button = self.driver.find_element(
                By.CSS_SELECTOR, 
                "a.k-link.k-pager-nav[aria-label*='next page']"
            )
            
            # Verify it's the next page button (not previous/other)
            if "next" in next_button.get_attribute("aria-label").lower():
                return next_button
                
            return None
            
        except NoSuchElementException:
            return None
        except Exception as e:
            self.logger.warning(f"Error finding next page button: {str(e)}")
            return None

    def scrape_articles(self):
        """Scrape articles from WHO website with pagination support"""
        base_url = 'https://www.who.int/news'
        
        try:
            self.logger.info(f"Scraping articles from {base_url}")
            self.driver.get(base_url)
            time.sleep(2)  # Wait for page to load
            
            # Scrape articles with pagination
            articles = self.scrape_with_pagination(max_pages=5)  # Adjust max_pages as needed
            seen_urls = set()
            
            for article in articles:
                try:
                    # Skip duplicates
                    if article['link'] in seen_urls:
                        continue
                    
                    # Classify the article
                    classification = self._classify_article(article['title'])
                    
                    full_article = {
                        'title': article['title'],
                        'link': article['link'],
                        'date': article['date'],
                        'preamble': article.get('preamble', ''),  # Using document type as preamble
                        'image_url': article.get('image_url', ''),  # Adding image URL
                        'document_type': classification['document_type'],
                        'product_type': classification['product_type'],
                        'document_confidence': classification['document_confidence'],
                        'product_confidence': classification['product_confidence']
                    }
                    seen_urls.add(article['link'])
                    
                    self.logger.info(
                        f"Added article: {article['title'][:50]}... | "
                        f"Date: {article['date']} | "
                        f"Type: {classification['document_type']} "
                        f"({classification['document_confidence']}%)"
                    )
                    
                    # Process the article
                    processed = self._process_article(full_article, base_url)
                    if processed:
                        self.data_rows.append(processed)
                        
                except Exception as e:
                    self.logger.warning(f"Error processing article: {str(e)}")
                    continue
                    
        except Exception as e:
            self.logger.error(f"Scraping failed: {str(e)}")
            import traceback
            traceback.print_exc()
        finally:
            self.save_results()


    def _classify_article(self, text):
        """Classify article text into document and product types"""
        text = text.lower()
        classification = {
            'document_type': 'Other Type',
            'product_type': 'Other',
            'document_confidence': 0,
            'product_confidence': 0
        }
        
        # Document classification
        for doc_type, keywords in self.DOCUMENT_TYPES.items():
            matches = sum(1 for kw in keywords if kw in text)
            confidence = min(100, (matches / len(keywords)) * 100 if keywords else 0)
            if confidence > classification['document_confidence']:
                classification.update({
                    'document_type': doc_type,
                    'document_confidence': round(confidence, 1)
                })
        
        # Product classification
        for prod_type, keywords in self.PRODUCT_TYPES.items():
            matches = sum(1 for kw in keywords if kw in text)
            confidence = min(100, (matches / len(keywords)) * 100 if keywords else 0)
            if confidence > classification['product_confidence']:
                classification.update({
                    'product_type': prod_type,
                    'product_confidence': round(confidence, 1)
                })
                
        return classification

    def _retry_on_stale(self, locator, max_attempts=3):
        """Retry action when encountering stale element exceptions"""
        attempt = 0
        last_exception = None
        
        while attempt < max_attempts:
            try:
                element = WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located(locator)
                )
                return element
            except StaleElementReferenceException as e:
                last_exception = e
                attempt += 1
                time.sleep(1)
        
        raise last_exception

    def _process_article(self, article: Dict, base_url: str) -> Optional[Dict]:
        """Process article and extract information with retry logic"""
        attempts = 0
        max_attempts = 2

        while attempts < max_attempts:
            try:
                # Extract original content
                full_text = self._extract_article_content(article['link'])
                if not full_text:
                    return None

                # Detect language from original full text
                original_combined_text = f"{article['title']} {full_text}".lower()
                language = self.detect_languages(original_combined_text)

                # Then translate
                title_en = self.translate_to_english(article['title'])
                full_text_en = self.translate_to_english(full_text)

                summary_en = self.translate_to_english(self.generate_summary(full_text))

                # Extract drug names
                combined_text = f"{title_en} {full_text_en}"
                drug_names = self.extract_drug_names(combined_text)


                # Detect countries and regions
                combined_text_lower = f"{title_en} {full_text_en}".lower()
                countries = self.detect_countries(combined_text_lower)
                regions = self.map_regions(countries)
                language = self.detect_languages(combined_text_lower)

                # Construct processed article
                processed_article = {
                    'Title': title_en,
                    'Summary': summary_en,
                    'Date': self.format_date(article['date']),
                    'Source URL': base_url,
                    'Article URL': article['link'],
                    'Document_Type': article.get('document_type', 'Other Type'),
                    'Product_Type': article.get('product_type', 'Other'),
                    'Countries': ', '.join(set(countries)) if countries else None,
                    'Regions': ', '.join(set(regions)) if regions else None,
                    'Drug_names': ', '.join(drug_names) if drug_names else "None",
                    'Language': language[0] if language else "Unknown",
                    'Classification Confidence': f"{article.get('document_confidence', 0)}%",
                    'Product Confidence': f"{article.get('product_confidence', 0)}%"
                }

                return processed_article

            except StaleElementReferenceException:
                attempts += 1
                self.logger.warning(f"Stale element encountered. Retrying... ({attempts}/{max_attempts})")
                time.sleep(1)
            except Exception as e:
                self.logger.error(f"Error processing article: {str(e)}")
                return None  # ⚠️ FIX: Don't return undefined variable
        return None


    def save_results(self):
        """Save results to Excel with classification columns"""
        try:
            df = pd.DataFrame(self.data_rows, columns=[
                'Title', 'Summary', 'Article URL', 'Date',
                'Document_Type', 'Product_Type',
                'Countries', 'Regions', 'Drug_names',
                'Language', 'Source URL'  # ADDED Language
            ])

            df.to_excel(self.output_file, index=False, engine='openpyxl')
            print(f"✅ Data saved to {self.output_file}")
        except Exception as e:
            self.logger.error(f"Failed to save Excel: {e}")

    def _handle_consent_popup(self):
        """Handle cookie consent popup if present"""
        try:
            consent_button = WebDriverWait(self.driver, 5).until(
                EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'Accept')]"))
            )
            consent_button.click()
            time.sleep(1)
        except Exception:
            pass  # No popup found or already accepted
        
    def _extract_article_metadata(self) -> List[Dict]:
        """Extract article metadata from WHO news entries"""
        articles = []
        try:
            # Wait for articles to load
            WebDriverWait(self.driver, 20).until(
                EC.presence_of_all_elements_located((By.CSS_SELECTOR, ".link-container.table"))
            )
            
            # Find all article elements
            article_blocks = self.driver.find_elements(By.CSS_SELECTOR, ".link-container.table")
            self.logger.info(f"Found {len(article_blocks)} news entries")
            
            for article in article_blocks[:15]:
                try:
                    # Extract metadata elements
                    title = article.find_element(By.CSS_SELECTOR, ".heading").text.strip()
                    date = article.find_element(By.CSS_SELECTOR, ".timestamp").text.strip()
                    link = article.get_attribute('href')
                    
                    # Extract document type (News release, etc.)
                    doc_type = ""
                    try:
                        doc_type = article.find_element(By.CSS_SELECTOR, ".sf-tags-list-item").text.strip()
                    except:
                        pass
                    
                    # Extract image URL from background-image style
                    img_url = ""
                    try:
                        img_element = article.find_element(By.CSS_SELECTOR, ".background-image")
                        img_url = img_element.value_of_css_property("background-image")[5:-2]  # Removes 'url("")'
                    except:
                        pass
                    
                    # Make URL absolute if relative
                    if not link.startswith('http'):
                        base_url = "https://www.who.int"
                        link = urljoin(base_url, link)
                    
                    articles.append({
                        'title': title,
                        'link': link,
                        'date': date,
                        'image_url': img_url,
                        'preamble': doc_type  # Using document type as preamble
                    })
                    
                    self.logger.info(f"Added article: {title} | Date: {date} | Type: {doc_type}")
                    
                except Exception as e:
                    self.logger.warning(f"Error extracting article metadata: {str(e)}")
                    continue
                    
        except Exception as e:
            self.logger.error(f"Failed to extract article metadata: {str(e)}")
            import traceback
            traceback.print_exc()
            
        return articles
    
    def _extract_article_content(self, url: str) -> Optional[str]:
        """
        Extract main content from WHO article pages
        Args:
            url: URL of the article page to scrape
        Returns:
            Cleaned text content or None if extraction fails
        """
        try:
            self.logger.info(f"Extracting content from: {url}")
            self.driver.get(url)
            
            # Wait for main content to load
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "article.sf-detail-body-wrapper"))
            )
            
            # Priority selectors for WHO site
            selectors = [
                "article.sf-detail-body-wrapper",  # Main article container
                "div.sf_colsIn",                    # Content column
                "div[data-sf-element='Column 1']",  # Column identifier
                "div[class*='content']",            # Generic content div fallback
                "article",                          # Article tag fallback
                "main"                              # Main tag fallback
            ]
            
            for selector in selectors:
                try:
                    content = self.driver.find_element(By.CSS_SELECTOR, selector)
                    if content and content.text.strip():
                        # Clean and normalize the text
                        cleaned_text = self._clean_extracted_text(content.text)
                        return cleaned_text
                except NoSuchElementException:
                    continue
                except StaleElementReferenceException:
                    self.logger.warning(f"Stale element with selector: {selector}")
                    continue
            
            self.logger.warning(f"No content found using standard selectors for: {url}")
            return None
            
        except TimeoutException:
            self.logger.error(f"Timeout waiting for content to load: {url}")
            return None
        except Exception as e:
            self.logger.error(f"Content extraction failed for {url}: {str(e)}")
            return None

    def _clean_extracted_text(self, raw_text: str) -> str:
        """
        Clean and normalize extracted text content
        Args:
            raw_text: The raw text extracted from the page
        Returns:
            Cleaned and normalized text
        """
        # Remove empty paragraphs and excessive whitespace
        text = re.sub(r'(&nbsp;|\s{2,})', ' ', raw_text)
        
        # Normalize line breaks and remove leading/trailing whitespace
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        
        # Join with single newlines and ensure proper spacing
        return '\n'.join(lines)
            
    def generate_summary(self, text, word_limit=100):
        """Generate concise summary from full text"""
        if not text:
            return "No summary available"
        
        # Clean up text
        text = re.sub(r'\.\.\.|&nbsp;|\s{2,}', ' ', text)  # Remove HTML artifacts
        
        # Try to extract the first meaningful paragraph after the title
        paragraphs = [p.strip() for p in text.split('\n\n') if p.strip()]
        for p in paragraphs:
            if len(p.split()) > 15 and p.endswith('.'):  # Proper paragraph criteria
                sentences = re.split(r'(?<=[.!?])\s+', p)
                if sentences:
                    return sentences[0]  # Return first complete sentence
                
        # Fallback to first X words
        words = text.split()
        return ' '.join(words[:word_limit]) + ('...' if len(words) > word_limit else '')
    
    def format_date(self, date_str):
        """Convert various date formats to dd/mm/yyyy"""
        if not date_str or not date_str.strip():
            return "Unknown"
    
        date_str = date_str.replace("Publicerades:", "").strip()
    
        # Handle Swedish month names
        month_map = {
            'januari': '01', 'februari': '02', 'mars': '03', 'april': '04',
            'maj': '05', 'juni': '06', 'juli': '07', 'augusti': '08',
            'september': '09', 'oktober': '10', 'november': '11', 'december': '12'
        }
    
        # Match Swedish textual date: "21 juli 2025"
        swedish_pattern = re.match(r"(\d{1,2})\s+([a-zA-ZåäöÅÄÖ]+)\s+(\d{4})", date_str, re.IGNORECASE)
        if swedish_pattern:
            day, month_word, year = swedish_pattern.groups()
            month = month_map.get(month_word.lower())
            if month:
                return f"{day.zfill(2)}/{month}/{year}"
    
        # Known numeric formats
        formats_to_try = [
            "%d-%m-%Y",  # 21-07-2025
            "%Y-%m-%d",  # 2025-07-21
            "%d.%m.%Y",  # 21.07.2025
            "%d/%m/%Y",  # 21/07/2025 (already correct)
            "%B %d, %Y", # July 21, 2025
            "%b %d, %Y"  # Jul 21, 2025
        ]
    
        for fmt in formats_to_try:
            try:
                parsed = datetime.strptime(date_str, fmt)
                return parsed.strftime("%d/%m/%Y")
            except ValueError:
                continue
    
        # Fallback: return input if all parsing fails
        return date_str
      
    
    def translate_to_english(self, text):
        if not text.strip():
            return text
        try:
            return GoogleTranslator(source='auto', target='en').translate(text)
        except Exception as e:
            print(f"Translation failed: {e}. Using original text.")
            return text  # Fallback to original           

    def detect_languages(self, text):
        """Detect document language with focus on accuracy"""
        lang_phrases = {
            'english': ['in english', 'english version', 'original in english'],
            'multilingual': ['available in', 'translated version', 'languages:']
            }
        
        text_lower = text.lower()
        for phrase in lang_phrases['multilingual']:
            if phrase in text_lower:
                return ['Multiple']  

            for phrase in lang_phrases['english']:
                if phrase in text_lower:
                    return ['English']

            try:
                return [self.LANGUAGE_NAMES.get(detect(text), 'Unknown')]
            except:
                return ['Unknown']

    
    def detect_countries(self, text):
        """Detect countries/regions mentioned in text"""
        detected = []
        text = text.lower()
        for country, patterns in self.COUNTRY_PATTERNS.items():
            if any(re.search(r'\b' + pattern + r'\b', text) for pattern in patterns):
                detected.append(country)
        return detected if detected else ['Global']
    
    def map_regions(self, countries: List[str]) -> List[str]:
        """Map countries to their respective regions"""
        if not countries:
            return []
        
        regions = []
        for country in countries:
            region = self.REGION_MAPPING.get(country, 'Global')
            if region not in regions:
                regions.append(region)
        return regions

    def classify_document(self, text):
        """Classify document based on keywords"""
        text = text.lower()
        for doc_type, keywords in self.DOCUMENT_TYPES.items():
            if any(keyword in text for keyword in keywords):
                return doc_type
        return 'Other Type'

    def classify_product(self, text):
        """Classify product based on keywords"""
        text = text.lower()
        for product_type, keywords in self.PRODUCT_TYPES.items():
            if any(keyword in text for keyword in keywords):
                return product_type
        return 'Other'

if __name__ == "__main__":
    scraper = WHOnews(output_file='WHOnews.xlsx')
    try:
        scraper.scrape_articles()
    finally:
        scraper.cleanup()

