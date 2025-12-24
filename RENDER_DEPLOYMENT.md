# Deploying AURA to Render

This guide will help you deploy your AURA music recommendation system to Render.

## Prerequisites

1. A [Render account](https://render.com) (free tier works)
2. Your code pushed to a Git repository (GitHub, GitLab, or Bitbucket)

## Deployment Steps

### Option 1: Deploy via Render Dashboard (Recommended)

1. **Push your code to GitHub/GitLab/Bitbucket**
   ```bash
   git add .
   git commit -m "Prepare for Render deployment"
   git push origin main
   ```

2. **Create New Web Service on Render**
   - Go to [render.com/dashboard](https://dashboard.render.com)
   - Click "New +" → "Web Service"
   - Connect your Git repository

3. **Configure Service Settings**
   - **Name**: `aura-music-app` (or your preferred name)
   - **Environment**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn src.api.main:app --host 0.0.0.0 --port $PORT`
   - **Plan**: Free (or paid for better performance)

4. **Add Environment Variables**
   Go to Environment → Add Environment Variable:
   
   **Required:**
   ```
   USE_ONLINE_LLM=true
   LLM_API_PROVIDER=huggingface
   HUGGINGFACE_API_KEY=your_hf_api_key_here
   ```
   
   **Optional but Recommended:**
   ```
   YOUTUBE_API_KEY=your_youtube_api_key_here
   GEMINI_API_KEY=your_gemini_api_key_here
   ALLOWED_ORIGINS=https://your-app.onrender.com
   ```

5. **Set Up PostgreSQL Database (Required)**
   - In Render Dashboard, click "New +" → "PostgreSQL"
   - Create a new PostgreSQL database
   - Copy the **Internal Database URL**
   - Add as environment variable: `DATABASE_URL=postgresql://...`

6. **Deploy**
   - Click "Create Web Service"
   - Wait for deployment to complete (5-10 minutes)
   - Your app will be live at `https://your-app.onrender.com`

### Option 2: Use render.yaml (Automated)

If you have `render.yaml` in your repo:

1. Go to Render Dashboard
2. Click "New +" → "Blueprint"
3. Connect your repository
4. Render will automatically detect `render.yaml` and configure everything

## Post-Deployment Configuration

### 1. Configure Database

The app will automatically initialize the database on first startup. If you need to manually initialize:

```bash
# SSH into your Render service (if available) or run locally with DATABASE_URL set
python setup_database.py
```

### 2. Verify Environment Variables

Make sure these are set in Render Dashboard → Environment:
- `DATABASE_URL` (from Render PostgreSQL)
- `USE_ONLINE_LLM=true`
- `LLM_API_PROVIDER=huggingface`
- `HUGGINGFACE_API_KEY=your_key`
- `ALLOWED_ORIGINS=https://your-app.onrender.com` (your Render URL)

### 3. Test Your Deployment

1. Visit `https://your-app.onrender.com`
2. Check API docs at `https://your-app.onrender.com/docs`
3. Test health endpoint: `https://your-app.onrender.com/health`

## Troubleshooting

### Issue: Application Won't Start

**Check:**
- Build logs in Render Dashboard
- Ensure `Procfile` or start command is correct
- Verify all dependencies in `requirements.txt`

**Solution:**
- Check Render logs: Dashboard → Your Service → Logs
- Verify Python version matches `runtime.txt`
- Ensure `$PORT` environment variable is used (Render sets this automatically)

### Issue: Static Files Not Loading

**Solution:**
- Verify `static/` directory exists in your repo
- Check that static files are being served at `/static/` path
- Ensure CSP headers allow necessary resources

### Issue: Database Connection Errors

**Solution:**
- Verify `DATABASE_URL` is set correctly
- Check that PostgreSQL database is running
- Ensure database credentials are correct
- The app falls back to SQLite if PostgreSQL is unavailable (not recommended for production)

### Issue: CORS Errors

**Solution:**
- Add your Render URL to `ALLOWED_ORIGINS`:
  ```
  ALLOWED_ORIGINS=https://your-app.onrender.com,http://localhost:8000
  ```
- Render automatically sets `RENDER_EXTERNAL_URL` which the app uses

### Issue: API Timeouts

**Solution:**
- Render free tier has timeout limits
- Consider upgrading to paid plan for longer timeouts
- Optimize model loading (use online APIs instead of local models)

### Issue: Build Fails

**Common Causes:**
- Missing dependencies in `requirements.txt`
- Python version mismatch
- Large files exceeding limits

**Solution:**
- Check build logs for specific errors
- Ensure `runtime.txt` specifies correct Python version
- Remove large model files (use `.gitignore` or `.renderignore`)

## Environment Variables Reference

```bash
# Required
DATABASE_URL=postgresql://user:password@host:port/dbname
USE_ONLINE_LLM=true
LLM_API_PROVIDER=huggingface
HUGGINGFACE_API_KEY=your_hf_api_key_here

# Optional but Recommended
YOUTUBE_API_KEY=your_youtube_api_key_here
GEMINI_API_KEY=your_gemini_api_key_here
ALLOWED_ORIGINS=https://your-app.onrender.com

# Database (if not using DATABASE_URL)
DB_HOST=your-host.com
DB_PORT=5432
DB_NAME=aura_music
DB_USER=your_user
DB_PASSWORD=your_password
```

## Render-Specific Features

### Auto-Deploy
- Render automatically deploys on every push to your main branch
- You can disable this in Settings → Auto-Deploy

### Health Checks
- Render automatically checks `/health` endpoint
- Ensure this endpoint returns 200 OK

### Custom Domain
- Go to Settings → Custom Domain
- Add your domain and configure DNS

### Environment Variables
- Set in Dashboard → Environment
- Can be different for Preview and Production environments

## Monitoring

1. **View Logs**: Dashboard → Your Service → Logs
2. **Metrics**: Dashboard → Metrics (paid plans)
3. **Alerts**: Set up email notifications for deployment status

## Production Recommendations

1. **Use PostgreSQL**: Don't rely on SQLite for production
2. **Set Up Backups**: Configure automatic PostgreSQL backups
3. **Monitor Performance**: Upgrade to paid plan for better performance
4. **Use Environment Variables**: Never commit secrets to git
5. **Enable HTTPS**: Render provides free SSL certificates
6. **Set Up Custom Domain**: For better branding

## Support

- [Render Documentation](https://render.com/docs)
- [Render Community](https://community.render.com)
- Check application logs in Render Dashboard for specific errors

