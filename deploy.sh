#!/usr/bin/env bash
# Set up Google Cloud for Amtsbrief and deploy it to Cloud Run. Run from the project root.
# Safe to run again: every setup step checks whether it's already done.
#
# Before the first run, in the Firebase console (https://console.firebase.google.com):
#   1. Add Firebase to the existing Google Cloud project.
#   2. Authentication > Sign-in method: enable Google.
#   3. Project settings > Your apps: add a Web app. FIREBASE_API_KEY and FIREBASE_APP_ID
#      below come from its config (public values, not secrets).
set -euo pipefail

PROJECT=amtsbrief
REGION=europe-west3                      # Frankfurt: the app and its data stay in Germany
SERVICE=amtsbrief
SA="amtsbrief-run@${PROJECT}.iam.gserviceaccount.com"
: "${FIREBASE_API_KEY:?set FIREBASE_API_KEY from the Firebase web app config}"
: "${FIREBASE_APP_ID:?set FIREBASE_APP_ID from the Firebase web app config}"

gcloud config set project "$PROJECT" >/dev/null

echo "== APIs"
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com \
  firestore.googleapis.com identitytoolkit.googleapis.com aiplatform.googleapis.com

echo "== Firestore (Native mode, $REGION)"
gcloud firestore databases describe --database="(default)" >/dev/null 2>&1 \
  || gcloud firestore databases create --database="(default)" --location="$REGION"

echo "== Service account: may call Gemini and use Firestore, nothing else"
gcloud iam service-accounts describe "$SA" >/dev/null 2>&1 \
  || gcloud iam service-accounts create amtsbrief-run --display-name="Amtsbrief on Cloud Run"
for role in roles/aiplatform.user roles/datastore.user; do
  gcloud projects add-iam-policy-binding "$PROJECT" --member="serviceAccount:$SA" --role="$role" \
    --condition=None >/dev/null
done

echo "== Build and deploy (Cloud Build builds the Dockerfile)"
# max-instances caps the bill; concurrency 4 because each request can take 30 s of model calls.
gcloud run deploy "$SERVICE" --source . --region "$REGION" --service-account "$SA" \
  --allow-unauthenticated --memory 1Gi --cpu 1 --timeout 300 --concurrency 4 --max-instances 2 \
  --set-env-vars "GOOGLE_GENAI_USE_ENTERPRISE=true,GOOGLE_CLOUD_PROJECT=$PROJECT,GOOGLE_CLOUD_LOCATION=global" \
  --set-env-vars "FIREBASE_API_KEY=$FIREBASE_API_KEY,FIREBASE_APP_ID=$FIREBASE_APP_ID"

URL=$(gcloud run services describe "$SERVICE" --region "$REGION" --format='value(status.url)')
echo "== Deployed: $URL"
echo "Add ${URL#https://} to Firebase > Authentication > Settings > Authorized domains, or sign-in is refused."
