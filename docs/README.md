# Classroom Transcripts

Azure Functions app for transcribing classroom audio using AssemblyAI.

## Local Development

1. Install dependencies:

```bash
pip install -r requirements.txt
pip install -r src/functions/requirements.txt
```

2. Start Azurite for local storage:

```bash
docker run -d -p 10000:10000 -p 10001:10001 -p 10002:10002 mcr.microsoft.com/azure-storage/azurite
```

3. Set up environment variables:

```bash
op inject --in-file .env.onepassword --out-file .env.local
```

4. Run tests:

```bash
./scripts/run_integration_tests.sh
```

## Deployment

1. Create Azure Resources:

```bash
az group create --name classroom-transcripts-rg --location eastus
az storage account create --name classroomtranscripts --resource-group classroom-transcripts-rg
az functionapp create --name classroom-transcripts-func --resource-group classroom-transcripts-rg --storage-account classroomtranscripts --runtime python --runtime-version 3.11 --functions-version 4 --os-type linux
```

2. Configure GitHub Secrets:

- `AZURE_FUNCTIONAPP_PUBLISH_PROFILE`: Function app publish profile
- `ASSEMBLYAI_API_KEY`: AssemblyAI API key
- `AZURE_STORAGE_CONNECTION_STRING`: Azure Storage connection string
- `AZURE_FUNCTION_KEY`: Function app key

3. Deploy:

- Push to main branch or manually trigger the deployment workflow

## Monitoring

Monitor function execution:

```bash
az monitor app-insights query --app classroom-transcripts-func --analytics-query "traces | where timestamp > ago(5m) and severityLevel >= 2 | project timestamp, message, severityLevel" --resource-group classroom-transcripts-rg
```

# Classroom Transcript Web App

## Overview

This is a web app that supports teachers and curriculum coaches in analyzing classroom transcripts.

## Features

- Teachers can upload audio files and analyze them with a focus on the teacher's voice, the student's voice, and the overall classroom discussion.
- Uploaded audio files are transcribed and published to a Google Drive folder.
