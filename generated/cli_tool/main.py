import csv
import json
import sys
import click

class CSVToJSONError(Exception):
    """Custom exception for CSV to JSON conversion errors."""
    pass

@click.command()
@click.argument('input_file', type=click.Path(exists=True, readable=True))
@click.option('--output', '-o', 'output_file', type=click.Path(), help='Output JSON file path. If not provided, output is printed to stdout.')
def main(input_file: str, output_file: str) -> None:
    """
    Convert a CSV file to JSON format.
    
    Args:
        input_file: Path to the input CSV file.
        output_file: Optional path to the output JSON file. If not provided, output is printed to stdout.
    
    Example:
        csv_to_json.py data.csv --output output.json
        csv_to_json.py data.csv
    """
    try:
        # Read the CSV file
        with open(input_file, 'r', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            headers = reader.fieldnames
            if not headers:
                raise CSVToJSONError("CSV file is empty or has no header row.")
            
            # Convert each row to a JSON object
            data = []
            for row in reader:
                data.append(row)
            
            # Prepare output
            if output_file:
                # Write to file
                with open(output_file, 'w', encoding='utf-8') as jsonfile:
                    json.dump(data, jsonfile, indent=2, ensure_ascii=False)
                click.echo(f"Successfully converted {input_file} to {output_file}")
            else:
                # Print to stdout
                click.echo(json.dumps(data, indent=2, ensure_ascii=False))
                
    except FileNotFoundError:
        click.echo(f"Error: Input file '{input_file}' not found.", err=True)
        sys.exit(1)
    except PermissionError:
        click.echo(f"Error: Permission denied when reading '{input_file}'.", err=True)
        sys.exit(1)
    except csv.Error as e:
        click.echo(f"Error: Malformed CSV file - {str(e)}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Error: Unexpected error occurred - {str(e)}", err=True)
        sys.exit(1)

if __name__ == '__main__':
    main()
