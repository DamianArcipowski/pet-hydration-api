# Smart Pet Hydration API

## General information
This repository contains the backend for a smart pet hydration system - REST API and database schema.

## Tech stack
- Python 3.10
- FastAPI 0.141.1
- MySQL Server 8.4.7

## How it works
1. In the root directory of a project run `python3 -m venv venv` to create a virtual environment
2. Then run `pip install -r requirements.txt` to install the necessary modules
3. Create environment variables which hold database connection details (Settings class in config.py) 
4. Finally go to the **app** directory and run `uvicorn main:app --host 0.0.0.0 --port 8080` to run the uvicorn server
5. All endpoints descriptions are available under **/docs**
