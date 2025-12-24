# Deploying AURA to Vercel

This guide will help you deploy your AURA music recommendation system to Vercel.

## Prerequisites

1. A [Vercel account](https://vercel.com/signup) (free tier works)
2. [Vercel CLI](https://vercel.com/docs/cli) installed (optional, but recommended)
3. Your code pushed to a Git repository (GitHub, GitLab, or Bitbucket)

## Important Notes

⚠️ **Limitations for Vercel Deployment:**

1. **Serverless Functions**: Vercel uses serverless functions, which means:
   - In-memory state (like `analysis_status` and `user_profiles`) won't persist across requests
   - Consider using a database (like Vercel Postgres, MongoDB, or Redis) for production
   
2. **Function Size Limits**: 
   - Maximum function size: 50MB (uncompressed)
   - Large ML models might exceed this limit
   - Consider using model hosting services or reducing model size

3. **Execution Timeout**:
   - Hobby plan: 10 seconds
   - Pro plan: 60 seconds
   - Long-running operations (like model loading) might timeout

## Deployment Steps

### Option 1: Deploy via Vercel Dashboard (Recommended)

1. **Push your code to GitHub/GitLab/Bitbucket**
   ```bash
   git add .
   git commit -m "Prepare for Vercel deployment"
   git push origin main
   ```

2. **Import Project to Vercel**
   - Go to [vercel.com/new](https://vercel.com/new)
   - Click "Import Git Repository"
   - Select your repository
   - Vercel will auto-detect the settings

3. **Configure Project Settings**
   - **Framework Preset**: Other
   - **Root Directory**: `./` (root of your project)
   - **Build Command**: Leave empty (no build needed)
   - **Output Directory**: Leave empty
   - **Install Command**: `pip install -r requirements.txt`

4. **Add Environment Variables** (if needed)
   - Go to Project Settings → Environment Variables
   - Add any API keys or configuration:
     ```
     ALLOWED_ORIGINS=https://your-domain.vercel.app
     ```

5. **Deploy**
   - Click "Deploy"
   - Wait for deployment to complete
   - Your app will be live at `https://your-project.vercel.app`

### Option 2: Deploy via Vercel CLI

1. **Install Vercel CLI**
   ```bash
   npm i -g vercel
   ```

2. **Login to Vercel**
   ```bash
   vercel login
   ```

3. **Deploy**
   ```bash
   vercel
   ```
   
   Follow the prompts:
   - Link to existing project or create new
   - Confirm settings
   - Deploy

4. **Deploy to Production**
   ```bash
   vercel --prod
   ```

## Post-Deployment Configuration

### 1. Configure Online LLM (Recommended)

**Important**: The system now uses online Llama models by default, which is perfect for Vercel!

1. **Get a Hugging Face API Key** (Free tier available):
   - Go to [huggingface.co/settings/tokens](https://huggingface.co/settings/tokens)
   - Create a new token (read access is enough)
   
2. **Add to Vercel Environment Variables**:
   ```
   USE_ONLINE_LLM=true
   LLM_API_PROVIDER=huggingface
   HUGGINGFACE_API_KEY=your_token_here
   ```

3. **Alternative Providers**:
   - **Replicate**: Set `REPLICATE_API_TOKEN` and `LLM_API_PROVIDER=replicate`
   - **OpenAI**: Set `OPENAI_API_KEY` and `LLM_API_PROVIDER=openai`

See [ONLINE_LLM_SETUP.md](./ONLINE_LLM_SETUP.md) for detailed instructions.

### 2. Update Frontend API URL

After deployment, update the frontend to use your Vercel URL:

The `index.html` already has auto-detection:
```javascript
const API_BASE = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
    ? 'http://localhost:8000/api/v1'
    : window.location.origin + '/api/v1';
```

This should work automatically, but verify it's using the correct URL.

### 2. Set Up PostgreSQL Database (Required!)

The application now uses PostgreSQL for storing user data and listening history.

**Option A: Vercel Postgres (Recommended for Vercel deployments)**

1. **Add Vercel Postgres to your project**:
   - Go to Vercel Dashboard → Your Project → Storage
   - Click "Create Database" → Select "Postgres"
   - Follow the setup wizard

2. **Get Connection String**:
   - Vercel automatically sets `POSTGRES_URL` environment variable
   - The app will automatically use it

3. **Initialize Database**:
   - The database is automatically initialized on first startup
   - Or run manually: `python setup_database.py`

**Option B: External PostgreSQL Database**

1. **Set up PostgreSQL** (choose one):
   - **Supabase** (free tier): https://supabase.com
   - **Neon** (free tier): https://neon.tech
   - **Railway** (free tier): https://railway.app
   - **Render** (free tier): https://render.com
   - **AWS RDS**, **Google Cloud SQL**, etc.

2. **Add Environment Variable**:
   ```
   DATABASE_URL=postgresql://user:password@host:port/dbname
   ```
   
   Or use individual components:
   ```
   DB_HOST=your-host.com
   DB_PORT=5432
   DB_NAME=aura_music
   DB_USER=your_user
   DB_PASSWORD=your_password
   ```

3. **Initialize Database**:
   ```bash
   python setup_database.py
   ```

**Note**: If no PostgreSQL credentials are provided, the app falls back to SQLite for local development.

### 3. Optimize Model Loading

If models are too large:

1. **Use Model Hosting Services**:
   - Hugging Face Inference API
   - Replicate
   - Modal

2. **Lazy Load Models**:
   - Load models on first request
   - Cache in global scope (within function limits)

3. **Reduce Model Size**:
   - Use smaller models
   - Quantize models
   - Use model distillation

## Troubleshooting

### Issue: Function Timeout

**Solution**: 
- Optimize model loading
- Use background jobs for long operations
- Consider Vercel Pro plan (60s timeout)

### Issue: Function Size Too Large

**Solution**:
- Remove unnecessary files from deployment
- Use `.vercelignore` to exclude large files
- Host models externally

### Issue: CORS Errors

**Solution**:
- Update `ALLOWED_ORIGINS` environment variable
- Include your Vercel domain in CORS settings

### Issue: State Not Persisting

**Solution**:
- Implement database storage
- Use Vercel KV or external database
- Don't rely on in-memory state

## Monitoring

1. **View Logs**: 
   - Vercel Dashboard → Your Project → Functions → View Logs

2. **Check Function Metrics**:
   - Vercel Dashboard → Analytics
   - Monitor execution time and errors

3. **Set Up Alerts**:
   - Vercel Dashboard → Settings → Notifications

## Production Recommendations

1. **Use Environment Variables** for sensitive data
2. **Set up a database** for state persistence
3. **Enable Vercel Analytics** for monitoring
4. **Set up custom domain** (optional)
5. **Configure rate limiting** if needed
6. **Set up error tracking** (Sentry, etc.)

## Example Environment Variables

```bash
# CORS
ALLOWED_ORIGINS=https://your-app.vercel.app

# Database (PostgreSQL)
DATABASE_URL=postgresql://user:password@host:port/dbname
# OR use individual components:
# DB_HOST=your-host.com
# DB_PORT=5432
# DB_NAME=aura_music
# DB_USER=your_user
# DB_PASSWORD=your_password

# LLM API
USE_ONLINE_LLM=true
LLM_API_PROVIDER=huggingface
HUGGINGFACE_API_KEY=your_hf_api_key_here
```

## Database Schema

The database automatically creates the following tables on first startup:

- **users**: User accounts and profiles
- **sessions**: Authentication sessions
- **songs**: Song metadata
- **user_songs**: User's song collections
- **listening_history**: Tracks when users listen to songs (for model analysis)
- **taste_profiles**: User taste profiles for recommendations

The database is initialized automatically when the app starts, or you can run:
```bash
python setup_database.py
```

## Support

- [Vercel Documentation](https://vercel.com/docs)
- [Vercel Python Runtime](https://vercel.com/docs/concepts/functions/serverless-functions/runtimes/python)
- [FastAPI on Vercel](https://vercel.com/guides/deploying-fastapi-with-vercel)

