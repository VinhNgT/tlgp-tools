import os
import json
import zipfile
import shutil
from typing import Tuple
from models import WorkspaceState

WORKSPACE_JSON_NAME = "workspace.json"

class WorkspaceIO:
    """Handles packing and unpacking WorkspaceState to/from .zip archives."""

    @staticmethod
    def pack_workspace(state: WorkspaceState, image_path: str, output_zip: str) -> str:
        """
        Packs a WorkspaceState and its corresponding raw image into a single .zip file.
        
        Args:
            state: The WorkspaceState pydantic model.
            image_path: The absolute path to the raw screenshot image file on disk.
            output_zip: The absolute path where the .zip file should be saved.
            
        Returns:
            The path to the created .zip file.
        """
        if not os.path.exists(image_path):
            raise FileNotFoundError(f"Source image not found: {image_path}")

        image_filename = os.path.basename(image_path)
        
        # Ensure the state references the correct image filename
        if state.image:
            state.image.filename = image_filename
            
        with zipfile.ZipFile(output_zip, 'w', zipfile.ZIP_DEFLATED) as zf:
            # Write the JSON state
            state_json = state.model_dump_json(indent=2)
            zf.writestr(WORKSPACE_JSON_NAME, state_json)
            
            # Write the raw image
            zf.write(image_path, arcname=image_filename)
            
        return output_zip

    @staticmethod
    def unpack_workspace(zip_path: str, extract_dir: str) -> Tuple[WorkspaceState, str]:
        """
        Unpacks a workspace .zip archive into the specified directory.
        
        Args:
            zip_path: Path to the .zip file.
            extract_dir: Directory where the contents should be extracted.
            
        Returns:
            A tuple of (WorkspaceState, absolute_path_to_extracted_image)
        """
        if not os.path.exists(zip_path):
            raise FileNotFoundError(f"Zip file not found: {zip_path}")

        os.makedirs(extract_dir, exist_ok=True)
        
        with zipfile.ZipFile(zip_path, 'r') as zf:
            zf.extractall(path=extract_dir)
            
        json_path = os.path.join(extract_dir, WORKSPACE_JSON_NAME)
        if not os.path.exists(json_path):
            raise ValueError(f"Invalid workspace archive: Missing {WORKSPACE_JSON_NAME}")
            
        with open(json_path, 'r', encoding='utf-8') as f:
            state_data = json.load(f)
            
        state = WorkspaceState.model_validate(state_data)
        
        image_path = None
        if state.image and state.image.filename:
            image_path = os.path.join(extract_dir, state.image.filename)
            if not os.path.exists(image_path):
                raise FileNotFoundError(f"Image referenced in workspace.json not found in archive: {state.image.filename}")
                
        return state, image_path
