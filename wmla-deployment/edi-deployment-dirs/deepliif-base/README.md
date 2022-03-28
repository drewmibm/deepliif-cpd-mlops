# README for DeepLIIF Deployment 

## Summary
Takes input image as 3d tensor and returns DeepLIIF-generated PIL images. To generate images, the deployment uses the `test` command found in `cli.py`, which executes code from the `deepliif/` code base. Image input can come from a remote source (e.g., PVC storage volume on CPD) or be included in the request payload as a serialized tensor. When from a remote source, returned images are also saved in the same remote source; when submitted in the request payload, outputted images are returned in the request response. Submission via a remote source is particularly useful when the input image is particularly large, and a request timeout is likely.

### Additional information
* The storage volume used during inference is specific to the deployment, and therefore input images from a remote source must be available in this storage volume. `VOLUME_DISPLAY_NAME` is specified during deployment submission; it is passed to the `--custom-arg` argument in `cli_mlops.py deploy create` command.
* Upon deployment, the kernel automatically creates a deployment-specific directory in `VOLUME_DISPLAY_NAME` with the path `edi_deployments/{deploy_name}`
    - `edi_deployments/{deploy_name}/edi_logs` collects logs and can be identified using the `MSD_POD_NAME` value, which is available from the WMLA console
    - `edi_deployments/{deploy_name}/output_dir/{TASK_JOB_ID}-{request-number}/` will contain the outputted response images if the request input comes from a remote source


## Payload
    - `local_input_image`: serialized input image as str
    - `img_path_on_pvc`: path to input image on PVC storage volume, path must be relative to root dir (e.g., edi_inference/input_images/*.png). If `local_input_image` and `img_path_on_pvc` are provided, the latter is prioritized
    - `tile_size`: Tile size as int, defaults to 512
    - `images_to_return`: one of (`all`,`modalities`,`seg_masks`) to return all output images, modalities only, or segmentation masks only. original IHC image returned in all cases.

## Response
    - If `img_path_on_pvc` is supplied:
        * JSON with path to outputted images on `VOLUME_DISPLAY_NAME`
    - If `local_input_image` is supplied:
        * JSON of DeepLIIF-gen images with names as keys and serialized tensors as values (if `local_input_image` supplied)
        * e.g., {"IHC":<str>, ... ,"Seg":<str>}
    
## Caller Example

### `img_path_on_pvc` is supplied

```
# From CPD
headers = {'Authorization': f'Bearer {os.getenv("USER_ACCESS_TOKEN")}'}
data = {
    'img_path_on_pvc':'edi_deployments/sample_input_images/22_2_real_A.png',
    'tile_size':512,
    'images_to_return':'all'
}
r = requests.post(DEPLOYMENT_URL, headers=headers,
                  json = data, verify = False)
r.text
```

### `local_input_image` is supplied

```
# From CPD
headers = {'Authorization': f'Bearer {os.getenv("USER_ACCESS_TOKEN")}'}
data = {
    'local_input_image':serialized_local_image,
    'tile_size':512,
    'images_to_return':'all'
}
r = requests.post(DEPLOYMENT_URL, headers=headers,
                  json = data, verify = False)
output = r.json()
output['images'].keys()
```
