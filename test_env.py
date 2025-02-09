import os


def check_env():
    required_vars = [
        "ASSEMBLYAI_API_KEY",
        "AZURE_STORAGE_ACCOUNT",
        "AZURE_TENANT_ID",
        "AZURE_CLIENT_ID",
        "AZURE_CLIENT_SECRET",
    ]

    print("Checking environment variables:")
    for var in required_vars:
        value = os.getenv(var)
        if value:
            print(f"✓ {var} is set")
            if value.startswith("$"):
                print(f"  Warning: {var} appears to be a template value")
        else:
            print(f"✗ {var} is not set")


if __name__ == "__main__":
    check_env()
