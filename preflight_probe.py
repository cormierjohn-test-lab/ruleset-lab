# A file that parses but raises NameError at runtime -- the exact bug the check
# exists to catch. Class-body names are not in scope outside the class.

class Context:
    ENVIRONMENT = "dev"
    REGION = "cus"


scope = f"kv-dbx-1-{ENVIRONMENT}-{REGION}"
