import json
import os
import re

# Function to detect encoding
def detect_encoding(file_path):
    import chardet
    with open(file_path, 'rb') as f:
        result = chardet.detect(f.read())
    return result['encoding']

# Function to sanitize filenames
def sanitize_filename(title):
    # Remove or replace invalid characters
    return re.sub(r'[\\/*?:"<>|]', "", title)

# Specify the file paths
titles_file = 'sorted_files.txt'
links_file = 'sorted_links.txt'
output_file = 'output.jsonl'

# Detect encoding
encoding = detect_encoding(titles_file)
print(f"Detected encoding for {titles_file}: {encoding}")

# If encoding is not detected, use a default encoding
encoding = 'ISO-8859-1'

# Initialize the set of all codes
all_codes = set()

# Read the Titles
try:
    with open(titles_file, 'r', encoding=encoding, errors='replace') as f:
        titles = [line.strip() for line in f if line.strip()]
except Exception as e:
    print(f"Error reading {titles_file}: {e}")
    titles = []

# Extract codes from titles and add to all_codes
for title in titles:
    code = title.split(' ')[0].strip()
    all_codes.add(code.lower())  # Assuming case-insensitive codes

# Read and Clean the Links
try:
    with open(links_file, 'r', encoding=encoding, errors='replace') as f:
        links = []
        seen = set()
        for line in f:
            link = line.strip()
            if link and link not in seen:
                seen.add(link)
                links.append(link)
except Exception as e:
    print(f"Error reading {links_file}: {e}")
    links = []

# Create a Mapping from Code to Link and add codes to all_codes
link_dict = {}
for link in links:
    code = link.strip().split('/')[-1]
    link_dict[code] = link
    all_codes.add(code.lower())

# Process Each Title and Generate JSON Objects
with open(output_file, 'w', encoding='ISO-8859-1') as outfile:
    count = 0
    for title in titles:
        # Extract the code from the title (assumes code is the first word)
        code = title.split(' ')[0].strip()

        # Get the corresponding link
        link = link_dict.get(code, 'Link not found')

        # Sanitize the title to create a valid filename
        filename = sanitize_filename(title) + '.txt'

        # Build the full path to the text file in AI_Knowledge_Base directory
        text_filename = os.path.join('AI_Knowledge_Base', filename)

        if os.path.exists(text_filename):
            try:
                with open(text_filename, 'r', encoding='ISO-8859-1', errors='replace') as text_file:
                    text = text_file.read().strip()
            except Exception as e:
                print(f"Error reading {text_filename}: {e}")
                text = 'Text file could not be read'
        else:
            text = 'Text file not found'

        # Find mentions of other codes in the text
        # Tokenize the text
        tokens = re.findall(r'\b\w+(?:\.\w+)?\b', text)
        tokens = [token.lower() for token in tokens]

        # Find intersection with all_codes, excluding the code of the current document
        mentions = set(tokens) & all_codes
        mentions.discard(code.lower())  # Remove the code of the current document

        # Convert mentions to a sorted list
        mentions = sorted(mentions)

        # Create the JSON object
        json_obj = {
            'title': title,
            'link': link,
            'text': text,
            'mentions': mentions,
            'docid': code
        }

        count += 1

        # print the progress in terms of number of lines processed
        print(f"Processed: {count} of a total of {len(titles)} {round((titles.index(title) + 1) / len(titles) * 100, 2)}%")

        # Write the JSON object to the JSONL file
        json_line = json.dumps(json_obj, ensure_ascii=False)
        outfile.write(json_line + '\n')

print(f"JSONL file '{output_file}' has been created successfully.")