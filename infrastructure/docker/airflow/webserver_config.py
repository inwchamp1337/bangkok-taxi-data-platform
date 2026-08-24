import os
from flask_appbuilder.security.manager import AUTH_DB

basedir = os.path.abspath(os.path.dirname(__file__))

# ----------------------------------------------------------------------
# Airflow Webserver Configuration — Auto-Login as Admin
# ----------------------------------------------------------------------
# Automatically authenticates public / guest access as Admin role
# so the UI is accessible without login prompts.
# ----------------------------------------------------------------------

AUTH_TYPE = AUTH_DB

# Grant Admin role to unauthenticated users
AUTH_ROLE_PUBLIC = "Admin"

# Application Title
APP_NAME = "Bangkok Taxi Orchestrator"
