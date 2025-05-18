import os
import logging
import asyncio
import uuid
from config import LOCAL_STORAGE_PATH
from services.cloud_storage import upload_to_cloud_storage
from shortGPT.config.api_db import ApiKeyManager, ApiProvider
from shortGPT.config.asset_db import AssetDatabase, AssetType
from shortGPT.engine.content_video_engine import ContentVideoEngine
from shortGPT.engine.content_translation_engine import ContentTranslationEngine
from shortGPT.engine.facts_short_engine import FactsShortEngine
from shortGPT.config.languages import Language
from shortGPT.audio.edge_voice_module import EdgeTTSVoiceModule, EDGE_TTS_VOICENAME_MAPPING

# Initialize logger
logger = logging.getLogger(__name__)

class ShortGPTService:
    def __init__(self):
        """Initialize ShortGPT service with API keys and asset database"""
        self._init_api_keys()
        self._init_asset_database()

    def _init_api_keys(self):
        """Initialize API keys using ApiProvider enum"""
        required_keys = {
            ApiProvider.OPENAI: os.getenv('OPENAI_API_KEY'),
            ApiProvider.PEXELS: os.getenv('PEXELS_API_KEY')
        }
        
        optional_keys = {
            ApiProvider.ELEVEN_LABS: os.getenv('ELEVENLABS_API_KEY')
        }

        # Check required keys
        missing_keys = [k for k, v in required_keys.items() if not v]
        if missing_keys:
            raise ValueError(f"Missing required API keys: {', '.join([k.value for k in missing_keys])}")

        # Set required keys
        for provider, key in required_keys.items():
            ApiKeyManager.set_api_key(provider, key)

        # Set optional keys if available
        for provider, key in optional_keys.items():
            if key:
                ApiKeyManager.set_api_key(provider, key)

    def _init_asset_database(self):
        """Initialize asset database and sync local assets"""
        # Create assets directory if it doesn't exist
        assets_dir = os.path.join(LOCAL_STORAGE_PATH, 'shortgpt_assets')
        os.makedirs(assets_dir, exist_ok=True)
        
        # Sync any existing local assets
        AssetDatabase.sync_local_assets()
        
        # Add default assets if provided in environment
        if default_music := os.getenv('DEFAULT_BACKGROUND_MUSIC'):
            AssetDatabase.add_remote_asset(
                'default_background_music',
                AssetType.BACKGROUND_MUSIC,
                default_music
            )
            
        if default_video := os.getenv('DEFAULT_BACKGROUND_VIDEO'):
            AssetDatabase.add_remote_asset(
                'default_background_video',
                AssetType.BACKGROUND_VIDEO,
                default_video
            )

    def _get_voice_module(self, language_code='EN', voice_gender='male'):
        """Get voice module based on language and gender"""
        try:
            lang = getattr(Language, language_code.upper())
        except AttributeError:
            raise ValueError(f"Unsupported language code: {language_code}")

        gender = voice_gender.lower()
        if gender not in ['male', 'female']:
            gender = 'male'

        voice_name = EDGE_TTS_VOICENAME_MAPPING[lang][gender]
        return EdgeTTSVoiceModule(voice_name)

    def _manage_assets(self, request_data, job_id):
        """Manage assets for video generation"""
        assets = {}
        temp_files = []

        # Create job-specific asset directory
        asset_dir = os.path.join(LOCAL_STORAGE_PATH, job_id, 'assets')
        os.makedirs(asset_dir, exist_ok=True)

        # Handle background music
        if background_music_url := request_data.get('background_music_url'):
            asset_name = f"bg_music_{uuid.uuid4().hex[:8]}"
            AssetDatabase.add_remote_asset(asset_name, AssetType.BACKGROUND_MUSIC, background_music_url)
            assets['background_music_name'] = asset_name
            temp_files.append(asset_name)
        else:
            try:
                assets['background_music_name'] = AssetDatabase.get_asset_link('default_background_music')
            except:
                assets['background_music_name'] = ""

        # Handle background video
        if background_video_url := request_data.get('background_video_url'):
            asset_name = f"bg_video_{uuid.uuid4().hex[:8]}"
            AssetDatabase.add_remote_asset(asset_name, AssetType.BACKGROUND_VIDEO, background_video_url)
            assets['background_video_name'] = asset_name
            temp_files.append(asset_name)
        else:
            try:
                assets['background_video_name'] = AssetDatabase.get_asset_link('default_background_video')
            except:
                assets['background_video_name'] = None

        return assets, temp_files

    async def create_short_video(self, request_data, job_id=None):
        """Create video content using ShortGPT engines with cloud storage support"""
        if not job_id:
            job_id = str(uuid.uuid4())

        temp_files = []
        try:
            # Setup engine parameters
            engine_type = request_data.get('engine_type', 'content').lower()
            language = request_data.get('language', 'EN')
            voice_gender = request_data.get('voice_gender', 'male')
            voice_module = self._get_voice_module(language, voice_gender)

            # Manage assets
            assets, asset_temp_files = self._manage_assets(request_data, job_id)
            temp_files.extend(asset_temp_files)

            # Create job directory
            job_dir = os.path.join(LOCAL_STORAGE_PATH, job_id)
            os.makedirs(job_dir, exist_ok=True)

            # Initialize appropriate engine
            if engine_type == 'translation':
                if not (src_url := request_data.get('source_url')):
                    raise ValueError("source_url is required for translation engine")

                engine = ContentTranslationEngine(
                    voice_module=voice_module,
                    src_url=src_url,
                    target_language=getattr(Language, language.upper()),
                    use_captions=request_data.get('use_captions', False)
                )

            elif engine_type == 'facts':
                if not (facts_type := request_data.get('facts_type')):
                    raise ValueError("facts_type is required for facts engine")

                engine = FactsShortEngine(
                    voice_module=voice_module,
                    facts_type=facts_type,
                    background_video_name=assets.get('background_video_name'),
                    background_music_name=assets.get('background_music_name'),
                    num_images=request_data.get('num_images', 5),
                    watermark=request_data.get('watermark'),
                    language=getattr(Language, language.upper())
                )

            else:  # Default content video engine
                if not (script := request_data.get('script')):
                    raise ValueError("script is required for content engine")

                engine = ContentVideoEngine(
                    voice_module=voice_module,
                    script=script,
                    background_music_name=assets.get('background_music_name'),
                    watermark=request_data.get('watermark'),
                    isVerticalFormat=request_data.get('vertical', False),
                    language=getattr(Language, language.upper())
                )

            # Generate content
            steps = []
            for step_num, step_logs in engine.makeContent():
                steps.append(step_logs)

            # Get output path
            local_video_path = engine.get_video_output_path()

            # Upload to cloud storage
            try:
                cloud_path = await upload_to_cloud_storage(local_video_path, job_id)
                logger.info(f"Video uploaded to cloud storage: {cloud_path}")

                return {
                    'status': 'success',
                    'message': 'Video created successfully',
                    'video_url': cloud_path,
                    'steps': steps,
                    'engine_type': engine_type,
                    'job_id': job_id
                }
            except Exception as upload_error:
                logger.error(f"Cloud storage upload error: {str(upload_error)}")
                raise RuntimeError(f"Failed to upload video to cloud storage: {str(upload_error)}")

        except Exception as e:
            logger.error(f"Error in create_short_video: {str(e)}")
            return {
                'status': 'error',
                'message': str(e)
            }

        finally:
            # Clean up temporary assets
            for asset_name in temp_files:
                try:
                    AssetDatabase.remove_asset(asset_name)
                except Exception as cleanup_error:
                    logger.warning(f"Failed to clean up asset {asset_name}: {str(cleanup_error)}")

            # Clean up local files
            try:
                if os.path.exists(job_dir):
                    import shutil
                    shutil.rmtree(job_dir)
            except Exception as cleanup_error:
                logger.warning(f"Failed to clean up job directory: {str(cleanup_error)}")
