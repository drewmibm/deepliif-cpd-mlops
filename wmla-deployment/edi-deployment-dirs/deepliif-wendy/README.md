# README for DeepLIIF Deployment on WMLA Elastic Distributed Inference Service

## Summary
Takes input image as 3d tensor and returns DeepLIIF-generated PIL images. Input image can be from a remote (e.g., called from storage volume with results saved to storage volume) or local (i.e., serialized tensor) source.

## Payload
    - `local_input_image`: serialized input image as str
    - `storage_volume_name`: Name of CPD storage volume name as str, defaults to DeepLIIFData
    - `img_path_on_pvc`: path to input image...for storage volume, path must be relative to root dir (e.g., edi_inference/input_images/*.png)
    - `save_path_on_pvc`: path to save output images...for storage volume, path must be relative to root dir (e.g., edi_inference/output_images). required if `img_path_on_pvc` is supplied.
    - `credentials`: dict of secrets; must include CPD `username` (str) and CPD `api_key` (str). required if `img_path_on_pvc` is supplied.
    - `tile_size`: Tile size as int, defaults to 512
    - `images_to_return`: one of (`all`,`modalities`,`seg_masks`) to return all output images, modalities only, or segmentation masks only. original IHC image returned in all cases.

## Response
    - JSON of DeepLIIF-gen images with names as keys and serialized tensors as values (if `local_input_image` supplied)
    - e.g., {"IHC":<str>, ... ,"Seg":<str>}
    
## Caller Example

1. Get token for inference
2. Send a Restful request to the endpoint
```
```