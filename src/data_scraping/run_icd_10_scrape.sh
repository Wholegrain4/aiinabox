#!/bin/bash
set -e

echo "Starting ICD-10 code scrape..."
Rscript /app/data_scraping/icd_10_code_scrape.R

echo "Starting ICD-10 description scrape..."
Rscript /app/data_scraping/icd_10_description_scrape.R

echo "Starting ICD-10 code text cleaner..."
Rscript /app/data_scraping/icd_10_code_txt_cleaner.R

echo "Data scraping sequence complete."
