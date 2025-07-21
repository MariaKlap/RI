from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException, TimeoutException, StaleElementReferenceException
from deep_translator import GoogleTranslator
from transformers import pipeline
import pandas as pd
import time
import re
import os
import logging
from urllib.parse import urljoin
from datetime import datetime
from typing import List, Dict, Optional
from scrapy.crawler import CrawlerProcess

class FDAnews:
    def __init__(self, output_file='FDA_news.xlsx'):
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.INFO)
        ch = logging.StreamHandler()
        ch.setLevel(logging.INFO)
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        ch.setFormatter(formatter)
        self.logger.addHandler(ch)

        self.output_file = output_file
        self.data_rows = []
        self.translator = GoogleTranslator(source='auto', target='en')

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
            col_terms = {t.strip().lower() for t in col_terms if t.strip()}
            terms.update(col_terms)


        self.drug_terms_set = terms
        print(f"✅ Loaded {len(self.drug_terms_set)} drug terms from TSV columns: {', '.join(allowed_columns)}")

        # Combine all column values into one lowercase set
        self.match_terms = set()

        for col in allowed_columns:
            if col in df.columns:
                self.match_terms.update(df[col].dropna().astype(str).str.lower().unique())




        # Browser setup
        options = Options()
        prefs = {
            "profile.default_content_settings.popups": 0,
            "profile.content_settings.exceptions.automatic_downloads.*.setting": 1,
            "profile.default_content_setting_values.automatic_downloads": 1,
            "profile.default_content_setting_values.popups": 0
        }
        options.add_experimental_option("prefs", prefs)
        
        service = Service(ChromeDriverManager().install())
        self.driver = webdriver.Chrome(service=service, options=options)

    def run(self):
        try:
            self.scrape_fda_guidance()
        except Exception as e:
            self.logger.error(f"Run error: {e}")
        finally:
            self.cleanup()

    def cleanup(self):
        try:
            self.driver.quit()
        except Exception as e:
            self.logger.warning(f"Driver cleanup error: {e}")

    def scrape_fda_guidance(self):
        self.logger.info("Scraping FDA guidance documents...")
        url = "https://www.fda.gov/regulatory-information/search-fda-guidance-documents"
        self.driver.get(url)

        WebDriverWait(self.driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, "//span[@aria-labelledby='select2-lcds-datatable-filter--product-container']"))
        ).click()
        WebDriverWait(self.driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, "//li[contains(text(), 'Drugs')]"))
        ).click()

        WebDriverWait(self.driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, "//span[@aria-labelledby='select2-lcds-datatable-filter--date-container']"))
        ).click()
        WebDriverWait(self.driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, "//li[contains(text(), 'Last 90 days')]"))
        ).click()

        WebDriverWait(self.driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, "//select[@aria-controls= 'DataTables_Table_0']"))
        ).click()
        WebDriverWait(self.driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, "//option[contains(text(), 'All')]"))
        ).click()

        time.sleep(3)

        try:
            table = self.driver.find_element(By.XPATH, "//table[@id='DataTables_Table_0']/tbody")
        except Exception as e:
            self.logger.error(f"Could not locate data table: {e}")
            return

        rows = table.find_elements(By.TAG_NAME, "tr")
        self.logger.info(f"Found {len(rows)} FDA entries")

        for row in rows:
            try:
                summary_element = row.find_element(By.XPATH, "./td[@tabindex]/a")
                summary_text = summary_element.text
                summary_link = summary_element.get_attribute("href")
            except:
                summary_text = ""
                summary_link = ""

            try:
                doc_element = row.find_element(By.XPATH, "./td[2]/a")
                doc_link = doc_element.get_attribute("href")
            except:
                doc_link = None

            try:
                date_text = row.find_element(By.CLASS_NAME, "sorting_1").text.strip()
                # Convert date format from MM/DD/YYYY to DD/MM/YYYY
                date_obj = datetime.strptime(date_text, "%m/%d/%Y")
                formatted_date = date_obj.strftime("%d/%m/%Y")
            except Exception as e:
                self.logger.warning(f"Date parsing failed: {e}")
                formatted_date = datetime.now().strftime("%d/%m/%Y")

            translated_summary = self.translate_to_english(summary_text)
            drug_names = self.extract_drug_names(translated_summary)
            detected_lang = self.detect_languages(translated_summary)[0]

            self.data_rows.append({
                "Title": translated_summary,
                "Summary": translated_summary,
                "Article URL": summary_link,
                "Date": formatted_date,
                "Document_Type": "Guidance",
                "Product_Type": "Drug Product",
                "Countries": "United States",
                "Regions": "North America",
                "Drug_names": ', '.join(drug_names) if drug_names else "None",
                "Language": detected_lang,
                "Source URL": url
            })

        self.save_results()

    def extract_drug_names(self, text: str, title: str = None) -> List[str]:
        """Improved drug name extraction with better pattern matching"""
        if not text.strip():
            return []

        matched = set()  # Using set to avoid duplicates
        
        # Combine title and text for better context
        full_text = f"{title or ''} {text}".lower()
        
        for term in self.drug_terms_set:
            # Skip very short terms to reduce false positives
            if len(term) < 4:
                continue
                
            # Create a regex pattern that matches whole words only
            pattern = r'(?<!\w)' + re.escape(term.lower()) + r'(?!\w)'
            
            # Search in the full text
            if re.search(pattern, full_text, flags=re.IGNORECASE):
                matched.add(term)
                
        return list(matched)


    def translate_to_english(self, text):
        if not text.strip():
            return text
        try:
            return self.translator.translate(text)
        except Exception as e:
            self.logger.warning(f"Translation failed: {e}")
            return text

    def detect_languages(self, text):
        if "english" in text.lower():
            return ["English"]
        return ["English"]

    def save_results(self):
        try:
            df = pd.DataFrame(self.data_rows, columns=[
                'Title', 'Summary', 'Article URL', 'Date', 'Document_Type', 'Product_Type',
                'Countries', 'Regions', 'Drug_names', 'Language', 'Source URL'
            ])
            df.to_excel(self.output_file, index=False, engine='openpyxl')
            print(f"✅ Data saved to {self.output_file}")
        except Exception as e:
            self.logger.error(f"Failed to save Excel: {e}")

if __name__ == "__main__":
    scraper = FDAnews()
    scraper.run()
