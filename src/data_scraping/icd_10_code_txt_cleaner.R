# Load the necessary libraries
library(stringr)

# List the files in the Knowledge Base folder
file_names <- list.files("/app/icd_10_codes/", full.names = T)

# Get the base file names
file_names_base <- list.files("/app/icd_10_codes/", full.names = F)

# Define a count variable
count <- 1

# Loop through the files
for(path in file_names){
  # Read the lines of the text file
  lines <- readLines(path)

  # Remove troublesome characters
  lines <- str_remove(lines, fixed("›"))
  lines <- str_remove(lines, fixed("……"))
  #lines <- str_replace_all(lines, fixed("ô"), "o")

  # Write the cleaned lines to a new text file
  writeLines(lines, paste0("/app/icd_10_codes_clean/", str_remove(file_names_base[count], ".txt"), ".txt"))

  # Increment the count
  count <- count + 1
}
