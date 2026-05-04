"""Entry point for the north branch service. Pure delegation to the shared app."""
from branches._shared.branch_app import run

if __name__ == "__main__":
    run()
