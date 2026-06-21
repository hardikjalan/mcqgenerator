from fastapi import FastAPI

app = FastAPI()

@app.get("/")
def home():
    return {"status": "Backend is running"}

@app.get("/hello")
def hello():
    return {"message": "Hello from FastAPI"}