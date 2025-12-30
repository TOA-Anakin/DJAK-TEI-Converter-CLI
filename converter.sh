#!/bin/bash

# Usage: ./converter.sh [environment] [xml_filename]
# environment: local | testing | production (default: local)
# xml_filename: (Optional) The name of the file in the input/ folder. 
#               If omitted, all .xml files in input/ will be processed.

ENVIRONMENT=${1:-local}
INPUT_FILENAME=${2}

DOCKER_COMPOSE_FILE=".docker/$ENVIRONMENT/docker-compose.yml"

if [ ! -f "$DOCKER_COMPOSE_FILE" ]; then
    echo "Error: Docker-compose file for '$ENVIRONMENT' environment not found."
    exit 1
fi

# --- Conversion Function ---
run_conversion() {
    local xml_file=$1 # Just the filename (e.g. "10_DJAK.xml")

    if [ ! -f "input/$xml_file" ]; then
        echo "Error: File 'input/$xml_file' does not exist."
        return
    fi

    # Get current datetime unique for this run
    local datetime=$(date +"%Y-%m-%d-%H-%M-%S")
    local basename=$(basename "$xml_file" .xml)
    local output_dir="output/${basename}_${datetime}"

    mkdir -p "$output_dir"

    echo "------------------------------------------------"
    echo "Processing: $xml_file"
    echo "Output to:  $output_dir"

    # Run the converter
    docker compose -f "$DOCKER_COMPOSE_FILE" run --rm converter python scripts/tei_convertor_final.py \
        -i "input/${xml_file}" \
        -c "output/${basename}_${datetime}/lost_comments.txt" \
        -a "output/${basename}_${datetime}/lost_apparatus.txt" \
        -p "output/${basename}_${datetime}/problematic_comments.txt" \
        > "${output_dir}/${basename}_TEI.xml"
}

# --- Main Logic ---

if [ -n "$INPUT_FILENAME" ]; then
    # 1. Single File Mode
    run_conversion "$INPUT_FILENAME"
else
    # 2. Bulk Mode
    echo "No filename provided. Starting bulk processing of all XML files in 'input/'..."
    
    # Check if files exist to avoid loop errors
    shopt -s nullglob
    files=(input/*.xml)
    
    if [ ${#files[@]} -eq 0 ]; then
        echo "No .xml files found in input/ directory."
        echo "Did you run ./odt2xml.sh first?"
        exit 0
    fi

    for filepath in "${files[@]}"; do
        filename=$(basename "$filepath")
        run_conversion "$filename"
    done
fi

echo "------------------------------------------------"
echo "All tasks completed."