import click

from . import main


@click.command()
def cli():
    main()

if __name__ == "__main__":
    cli()
