#!/bin/bash
# AWS Static Site Deployment Script

set -e

REGION="us-east-1"
PREFIX="static-site"
USE_CDN=false
DELETE_MODE=false
LIST_MODE=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --cdn) USE_CDN=true; shift ;;
        --name) PREFIX="$2"; shift 2 ;;
        --delete) DELETE_MODE=true; shift ;;
        --list) LIST_MODE=true; shift ;;
        --region) REGION="$2"; shift 2 ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

# List deployed sites
if $LIST_MODE; then
    echo "=== Your S3 Static Sites ==="
    aws s3api list-buckets --query 'Buckets[?starts_with(Name, `static-site-`) || starts_with(Name, `calculator-app-`)].Name' --output text | tr '\t' '\n'
    exit 0
fi

# Check for index.html
if [ ! -f "index.html" ]; then
    echo "Error: No index.html found in current directory"
    exit 1
fi

# Generate bucket name
BUCKET_NAME="${PREFIX}-$(whoami | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9]//g')-$(date +%s)"

echo "=== AWS Static Site Deploy ==="
echo "Bucket: $BUCKET_NAME"
echo "Region: $REGION"
echo ""

# Create bucket
echo "[1/4] Creating S3 bucket..."
aws s3 mb "s3://$BUCKET_NAME" --region "$REGION"

# Upload files with correct content types
echo "[2/4] Uploading files..."
for ext in html css js json png jpg jpeg gif svg ico woff woff2 ttf eot; do
    case $ext in
        html) CT="text/html" ;;
        css) CT="text/css" ;;
        js) CT="application/javascript" ;;
        json) CT="application/json" ;;
        png) CT="image/png" ;;
        jpg|jpeg) CT="image/jpeg" ;;
        gif) CT="image/gif" ;;
        svg) CT="image/svg+xml" ;;
        ico) CT="image/x-icon" ;;
        woff|woff2) CT="font/woff2" ;;
        ttf) CT="font/ttf" ;;
        eot) CT="application/vnd.ms-fontobject" ;;
    esac
    find . -maxdepth 3 -name "*.$ext" -type f 2>/dev/null | while read f; do
        aws s3 cp "$f" "s3://$BUCKET_NAME/${f#./}" --content-type "$CT" 2>/dev/null || true
    done
done

# Enable static website hosting
echo "[3/4] Enabling static website hosting..."
aws s3 website "s3://$BUCKET_NAME/" --index-document index.html --error-document error.html 2>/dev/null || \
aws s3 website "s3://$BUCKET_NAME/" --index-document index.html

# Configure public access
echo "[4/4] Configuring public access..."
aws s3api put-public-access-block --bucket "$BUCKET_NAME" \
    --public-access-block-configuration "BlockPublicAcls=false,IgnorePublicAcls=false,BlockPublicPolicy=false,RestrictPublicBuckets=false"

POLICY="{\"Version\":\"2012-10-17\",\"Statement\":[{\"Sid\":\"PublicReadGetObject\",\"Effect\":\"Allow\",\"Principal\":\"*\",\"Action\":\"s3:GetObject\",\"Resource\":\"arn:aws:s3:::$BUCKET_NAME/*\"}]}"
aws s3api put-bucket-policy --bucket "$BUCKET_NAME" --policy "$POLICY"

# Output URLs
echo ""
echo "=== Deployment Complete ==="
echo "S3 Website: http://$BUCKET_NAME.s3-website-$REGION.amazonaws.com"

# CloudFront (optional)
if $USE_CDN; then
    echo ""
    echo "Creating CloudFront distribution (this takes a few minutes)..."
    DIST_ID=$(aws cloudfront create-distribution \
        --origin-domain-name "$BUCKET_NAME.s3-website-$REGION.amazonaws.com" \
        --default-root-object index.html \
        --query 'Distribution.Id' --output text 2>/dev/null || echo "")
    
    if [ -n "$DIST_ID" ]; then
        DOMAIN=$(aws cloudfront get-distribution --id "$DIST_ID" --query 'Distribution.DomainName' --output text)
        echo "CloudFront: https://$DOMAIN"
        echo "Distribution ID: $DIST_ID (takes ~10 min to deploy)"
    else
        echo "CloudFront creation failed - use S3 URL above"
    fi
fi

# Save deployment info
echo "$BUCKET_NAME" > .aws-deploy-bucket
echo "Bucket name saved to .aws-deploy-bucket"
