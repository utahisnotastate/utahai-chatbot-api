gcloud run deploy utahai-chatbot-api \
  --source . \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --set-env-vars "PROJECT_ID=utahai,LOCATION=global,DATA_STORE_ID=utahai-knowledge-base"