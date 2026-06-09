🔐 Crypto Fraud Detection
A real-time cryptocurrency fraud detection API built with FastAPI and blockchain evidence tracking. Deployed live at crypto-fraud-detection-psi.vercel.app.

🚀 Features

Real-time fraud detection on crypto transactions
Blockchain evidence tracking
REST API with auto-generated Swagger docs (/docs)
CORS-enabled for cross-origin frontend integration
Health check endpoint
Deployable on Vercel / any cloud platform


🛠️ Tech Stack
LayerTechnologyFrameworkFastAPI 0.95.2ServerUvicorn 0.22.0ValidationPydantic 1.10.13TemplatesJinja2 3.1.2HTTPaiohttp 3.9.5Configpython-dotenv 1.0.0LanguagePython 3.x

📁 Project Structure
crypto_fraud-detection/
├── app/
│   └── api/
│       └── v1/         # API route handlers
├── main.py             # FastAPI app entry point
├── run.py              # Runner script
├── requirements.txt    # Python dependencies
├── runtime.txt         # Python runtime version
└── .gitignore

⚙️ Installation & Setup
1. Clone the repository
bashgit clone https://github.com/abhisheksinghbhumihar/crypto_fraud-detection.git
cd crypto_fraud-detection
2. Create a virtual environment
bashpython -m venv venv
source venv/bin/activate        # On Windows: venv\Scripts\activate
3. Install dependencies
bashpip install -r requirements.txt
4. Configure environment variables
Create a .env file in the root directory:
envPORT=8000
# Add any API keys or config needed by the app
5. Run the application
bashpython main.py
Or using Uvicorn directly:
bashuvicorn main:app --reload --host 0.0.0.0 --port 8000

📡 API Endpoints
MethodEndpointDescriptionGET/Root — service infoGET/healthHealth checkGET/docsInteractive Swagger UI*/api/v1/Fraud detection routes (see docs)
Example Response — /health
json{
  "status": "healthy",
  "service": "fraud-detection"
}

🌐 Live Demo
👉 https://www.linkedin.com/in/abhishek-kumar-973128403/

🤝 Contributing
Pull requests are welcome! For major changes, please open an issue first to discuss what you'd like to change.

Fork the repo
Create your feature branch: git checkout -b feature/my-feature
Commit your changes: git commit -m 'Add my feature'
Push to the branch: git push origin feature/my-feature
Open a Pull Request


📄 License
This project is open source. Feel free to use and modify it.
