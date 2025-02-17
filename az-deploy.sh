# Specifies a specific label to deploy to.
az containerapp update --source . --target-label b --revisions-mode labels -n carnegie-coaching -g classroom-transcripts-rg