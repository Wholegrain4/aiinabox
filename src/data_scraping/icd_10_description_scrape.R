library(RSelenium)
library(wdman)
library(rvest)
library(stringr)
library(jsonlite)
library(doParallel)
library(foreach)

# --- Helper Functions ---

# Extract everything after the last "/" in a string
extract_after_last_slash <- function(x) {
  pos <- regexpr("/[^/]*$", x)
  if (pos[1] != -1) {
    return(substring(x, pos + 1))
  } else {
    return(x)
  }
}

# Create an RSelenium driver using Chrome with custom options (GPU disabled, images off)
create_driver <- function(port_num) {
  chrome_opts <- list(
    chromeOptions = list(
      args = c("--disable-gpu",
               "--blink-settings=imagesEnabled=false",
               "--no-sandbox",
               "--disable-dev-shm-usage",
               "--headless",
               "user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36")
    )
  )
  
  rD <- rsDriver(
    browser = "chrome",
    chromever = "133.0.6943.53",
    port = port_num,
    extraCapabilities = chrome_opts,
    verbose = FALSE
  )
  
  return(rD)
}

split_into_chunks <- function(vec, n) {
  # Validate n
  if (!is.numeric(n) || length(n) != 1 || n < 1) {
    stop("'n' must be a single integer >= 1")
  }
  
  len <- length(vec)
  # If your vector is empty, return n empty chunks (or decide how you want to handle it)
  if (len == 0) {
    return(vector("list", n))
  }
  
  # Compute the size of each chunk (ceiling so as not to lose elements)
  chunk_size <- ceiling(len / n)
  result <- vector("list", n)
  
  start <- 1
  for (i in seq_len(n)) {
    end <- min(start + chunk_size - 1, len)
    if (start > len) {
      # If we've already used up all elements, store an empty vector
      result[[i]] <- vector(mode(vec), 0)
    } else {
      result[[i]] <- vec[start:end]
    }
    start <- end + 1
  }
  
  result
}


# --- Main Setup ---

base_url <- "https://www.icd10data.com"

# Read links from JSON and keep only unique links
link_array_json <- fromJSON(txt = "/app/icd_10_code_jsons/icd_10_code_links.json")
link_array <- unique(link_array_json[1,])

# Get names of already processed documents (by taking the part before the first space)
documents_retrieved <- list.files("/app/icd_10_codes/")

if (length(documents_retrieved) > 0) {
  # Process the file names if the directory isn't empty
  documents_retrieved <- unlist(lapply(documents_retrieved, function(x) sub(" .*", "", x)))
  
  # For each link, extract the identifying part (after the last "/")
  document_universe <- unlist(lapply(link_array, extract_after_last_slash))
  
  # Filter out links that have already been processed
  link_array <- link_array[ !document_universe %in% documents_retrieved ]
} else {
  message("No previously processed documents found; processing all links.")
}


# --- Parallel Processing Setup ---

# Define the number of parallel sessions (adjust based on your system)
num_sessions <- 10

# Split the links into chunks so each worker processes roughly the same number of links
link_chunks <- split_into_chunks(link_array, num_sessions)


# Define a set of ports for each parallel session (ensure these ports are free)
ports <- c(4446L, 4447L, 4448L, 4449L, 4450L, 4451L, 4452L, 4453L, 4454L, 4455L)

# A probability vector for random delays (to mimic human-like behavior)
random_prob <- c(0.1, 0.05, 0.3, 0.05, 0.05, 0.3, 0.05, 0.025, 0.025, 0.05)

# Define a shared log file (ensure this directory exists and is writable)
log_file <- "/app/icd_10_codes/scrape.log"
# Optionally clear the previous log file:
if (file.exists(log_file)) file.remove(log_file)

# Set up parallel backend
cl <- makeCluster(num_sessions)
registerDoParallel(cl)

# Process each chunk of links in parallel
results <- foreach(i = seq_along(link_chunks),
                   .packages = c("RSelenium", "rvest", "stringr", "jsonlite")) %dopar% {
                     
                     # Define a logging function for this worker
                     log_message <- function(msg) {
                       cat(sprintf("[%s] Worker %d: %s\n", Sys.time(), i, msg),
                           file = log_file, append = TRUE)
                     }
                     
                     log_message("Starting processing of assigned chunk.")
                     
                     # Launch an RSelenium Chrome session on the assigned port
                     rD <- create_driver(ports[i])
                     remDr <- invisible(rD$client)
                     
                     worker_count <- 0
                     total_links <- length(link_chunks[[i]])
                     
                     # Process each link assigned to this worker
                     for(link in link_chunks[[i]]) {
                       full_url <- paste0(base_url, link)
                       log_message(sprintf("Navigating to URL: %s", full_url))
                       remDr$navigate(full_url)
                       
                       # Allow time for the page to load
                       Sys.sleep(0.5)
                       
                       # Get and parse the page source
                       page_source <- remDr$getPageSource()[[1]]
                       page_html <- read_html(page_source)
                       
                       # Extract the body content text
                       body_content <- html_nodes(page_html, "div.body-content")
                       body_content_text <- html_text(body_content, trim = TRUE)
                       
                       # Remove a specific unwanted string from the text
                       search <- "propertag.cmd.push(function () { proper_display('icd10data_content_1'); });"
                       body_content_text <- str_remove(body_content_text, fixed(search))
                       
                       # Extract the diagnostic name from the header (if present)
                       diag_name <- html_nodes(page_html, "h2.codeDescription") %>% html_text(trim = TRUE)
                       diag_name <- ifelse(length(diag_name) > 0, diag_name[1], "")
                       
                       # Generate a file name based on the link and diagnostic name
                       positions <- str_locate_all(link, "/")[[1]]
                       if(nrow(positions) > 0) {
                         index <- positions[nrow(positions), "end"]
                       } else {
                         index <- 0
                       }
                       file_base <- substring(link, index + 1, nchar(link))
                       file_name <- paste0(file_base, " ", diag_name)
                       file_name <- str_replace_all(file_name, "/", " ")  # Replace any "/" with a space
                       
                       # Write the retrieved text to a file
                       file_path <- paste0("/app/icd_10_codes/", file_name, ".txt")
                       writeLines(body_content_text, file_path)
                       
                       # Pause for a random delay before processing the next link
                       random_wait <- sample(1:10, 1, replace = TRUE, prob = random_prob)
                       Sys.sleep(random_wait)
                       
                       worker_count <- worker_count + 1
                       log_message(sprintf("Processed %d of %d links", worker_count, total_links))
                     }
                     
                     # Close the RSelenium session for this worker
                     remDr$close()
                     rD$server$stop()
                     
                     log_message("Finished processing assigned chunk.")
                   }

# Shut down the parallel cluster
stopCluster(cl)
message("Parallel processing complete.")
