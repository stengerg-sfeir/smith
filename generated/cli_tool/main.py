import click
import csv
import json
import sys
import os
from typing import Optional, Dict, Any

@click.command()
@click.argument('input_file', type=click.Path(exists=True, readable=True))
@click.option('--output', '-o', 'output_file', type=click.Path(writable=True), default=None, help='Output JSON file path. If not provided, output goes to stdout.')
def main(input_file: str, output_file: Optional[str]) -> None:
    """
    Convert a CSV file to JSON using dynamic column name detection.
    """
    try:
        with open(input_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            headers = reader.fieldnames
            if headers is None:
                raise ValueError("CSV file is empty or malformed - no headers found.")
            
            data = []
            for row in reader:
                row_obj = {header: row[header] for header in headers}
                data.append(row_obj)
            
            # Output JSON
            if output_file:
                os.makedirs(os.path.dirname(output_file) if os.path.dirname(output_file) else '.', exist_ok=True)
                with open(output_file, 'w', encoding='utf-8') as out_f:
                    json.dump(data, out_f, indent=2, ensure_ascii=False)
                click.echo(f"Successfully wrote to {output_file}")
            else:
                click.echo(json.dumps(data, indent=2, ensure_ascii=False))
    
    except FileNotFoundError:
        click.echo(f"Error: Input file '{input_file}' not found.", err=True)
        sys.exit(1)
    except PermissionError:
        click.echo(f"Error: Permission denied when reading '{input_file}'.", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Error processing CSV file: {str(e)}", err=True)
        sys.exit(1)

if __name__ == '__main__':
    main()
