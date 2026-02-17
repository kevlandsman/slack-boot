"""Run the interactive Google OAuth flow: python -m services.google_auth"""
from services.google_auth import GoogleAuthManager


def main():
    auth = GoogleAuthManager()
    print("Starting Google OAuth flow...")
    print(f"Credentials file: {auth.credentials_path}")
    print(f"Token will be saved to: {auth.token_path}")
    print()
    auth.run_interactive_flow()
    print("\nAuthentication successful! Token saved.")


if __name__ == "__main__":
    main()
