# README for DeepLIIF Deployment 
The deployment based on [kernel.py](kernel.py) handles 2 types of input:
- a serialized image: good for relatively small images for which the whole request can be finished within 1-2 minutes; returning serialized predicted images in response
- a referenced image: a path reference to an image on a Cloud Pak for Data storage volume; returning the path reference to the predicted images on the same storage volume (**this is still synchronous**)

To generate images, the deployment uses the `cli.py test` command, which executes code from the `deepliif/` code base. 

## Request Input
- `img_path_on_pvc`: path to 1 input image on Cloud Pak for Data storage volume, must be relative to root dir (e.g., edi_inference/input_images/image.png); either this parameter or `local_input_image` needs to be specified; if both are provided, `img_path_on_pvc` will be used
- `local_input_image`: 1 serialized input image as str; either this parameter or `img_path_on_pvc` needs to be specified
- `tile_size` (optional): tile size as int, defaults to 512
- `images_to_return` (optional): `all` (all output images),`modalities` (modalities only), or `seg_masks` (segmentation masks only), defaults to `all`; the original input image is returned in all cases.
- `request_id` (optional): a unique request id that differentiates this request from any other requests; if not provided, a randome uuid will be generated; recommended to include when supplying `img_path_on_pvc`, because the predicted images will be saved to a folder using `request_id` as the name and it's good to ensure that the target folder is known, especially when status code 504 (API request timeout) is expected

## Response
### API request status code
|status code|description|
|-----------|-----------|
|200| success, or if an error happens during the computation process, you will see 200, but the custom error messages are returned in response|
|504| API request timeout: this timeout since Cloud Pak for Data 4.0.7 can be controlled mostly by the deployment parameter `task_execution_timeout` (still also influenced by the router); prior to 4.0.7, this timeout is also bounded by ngnix timeout|

### Response content
A json response that can be loaded as a python dictionary, with the following fields:
- `request_id`: the same request id as in the input, or a random one generated during the inference process when no request id is provided in input
- `status`: the status of the request; possible values include "submitted", "running", "finished", "error"
- `log`: key events happened, or long error messages such as the output if the subprocess command (`cli.py test`) fails
- `msg`: the summary one-liner
- `images` (only exists if serialized image is sent in input): a dictionary, with output image filename as key (e.g., local_SegOverlaid.png) and serialized image content as value

## Examples
Refer to [DeepLIIF Inference Request Demo](../../DeepLIIF%20Inference%20Request%20Demo.ipynb)

## Deployment Script Details
Useful environment variables can be found in [cheat_sheet_wmla](../../../docs/cheat_sheet_wmla.txt).

#### Credentials
CPD credentials (username and apikey) are needed to generate and refresh the bearer token used in:
- WML sdk client (to download model file when the kernel starts)
- storage volume api (if an image path is provided, to pull input images and write predictions back; also dumps custom logs to storage volume)

To avoid saving the credentials as plain text in a script to be versioned in git, similar to OpenScale custom metrics script, the credentials are supposed to be provided in the `python cli_mlops.py deploy create` command with flag `--custom-arg`, for example:
```
python cli_mlops.py deploy create --name deepliif --model-asset-id 41a9a8ff-dcaa-4f0f-beb5-2e1bbaa2f384 --kernel-filename kernel.py --custom-arg CPD_USERNAME=********** --custom-arg CPD_API_KEY=********** --custom-arg VOLUME_DISPLAY_NAME=AdditionalDeepLIIFVolume
```
It essentially inserts a line for each custom arg (e.g., `CPD_USERNAME = **********` into the kernel file on the fly for the rest of the script to use this variable `CPD_USERNAME`. This modification is applied to the copy of kernel script that is going to be submitted to WMLA; the original, git-versioned kernel script hence is not influenced.

#### Storage volume
It is assumed that the deployment API uses the same storage volume (to write predicted images and optionally custom log files to) as the input data. If this no longer holds, you may want to add an input parameter for storage volume name, and in the kernel file use the argument `volume_display_name` in `sv.download()` or `sv.upload()` to control which storage volume to interact with.

This storage volume currently is specified when creating the deployment, as shown in the above example.

#### Output to storage volume
The deployment writes the following files to the specified storage volume:
```
-- edi_deployments
  |-- <deployment name>
    |-- edi_logs # custom log files, one for each historical and running kernel, filename containing `$MSD_POD_NAME` as the identifier (kernel pod id, can be found in the WMLA console) 
      |-- <MSD pod name>_inference.log
      |-- ...
    |-- <request id>
      |-- input_dir # if the input is a serialized image, it will be written to the storage with filename "local.png"
        |-- ...
      |-- output_dir # predicted images
        |-- ...
```

#### Logs
There are 3 types of logs messages generated in this deployment:
- WMLA deployment log, only accessible to the MLOps team who creates and manages the deployment
  - `print()` messages are sent to stdout
  - `Kernel.log_info` and similar methods, messages are sent to stderr (not used in deepliif)
  - you can view the logs in WMLA console or using the WMLA inference CLI (dlim)
- response, accessible to end users
  - we use a list `log` where log messages can keep appending and a string value `msg` for summary key message
  - make sure no matter what happens, your inference code will not completely break (e.g., `raise exception` will completely break it), and **the API logic is always able to send some sort of message about what is going on / going wrong back to the end user, even when an error happens during the code execution**
- log messages dumped to storage volume, accessible to the MLOps team and optionally to the end users
  - this is useful when you want a centralized place to easily access logs across historical and running kernel pods for the deployment, or across historical and running deployments
  
#### Storage in deployment pods
As of now, each deployment has a deployment-specific directory with read & write access. This path can be found using environment variable `REDHARE_MODEL_PATH` (example value: `/opt/wml-edi/repo/deepliif-wendy/deepliif-wendy-20220211-211426`).

**This directory is shared by all the kernels**. What does it mean? For example, if you install additional packages under this directory, the installation process (ideally) only needs to happen once in the first kernel. The `pip install` command in new kernels started afterwards will be able to tell that these packages are already installed. (Things may not be this ideal if you start multiple kernels at the very beginning, where although kernel 1 started installation of package A, since kernel 2 executed the `pip install` command at almost the same time when kernel 1 hasn't finished installation, kernel 2 could try to install the same package A as well.)

    



