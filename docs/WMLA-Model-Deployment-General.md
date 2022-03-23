# WMLA Elastic Distributed Inference

WMLA offers elastic distributed inference (EDI) capabilities to create GPU-based inference services and deploy published models. The [**dlim** CLI tool](https://www.ibm.com/docs/en/wmla/2.3?topic=inferencedownload-configure-dlim-cli-tool) allows users to manage deployments programmatically. It can be used anywhere. Within Watson Studio, deployment dependencies are developed in JupyterLab or RStudio, and deployments are created via submissions to WMLA using `dlim`. Deployed models can be managed (e.g., started, stopped, edited) from the WMLA console directly, or using `dlim` for more granular usage.

This document is based on WMLA 2.3.5 on CPD 4.0.5.

## dlim tool

### Setup

`dlim` is a command line tool you can download directly from your WMLA console by navigating to `Help > Command Line Tools`. Within Watson Studio, the recommendation is to place this file in the git root directory `/userfs/dlim` (to persist the file), and add this path to the Linux `PATH` variable to facilitate usage.

In a JupyterLab environment within Watson Studio you can use the environment variable `HOME` which is equivalent to `/userfs` in a Project with default Git integration. For Python users, you can use the following code to complete this step:

```python
import os
import shutil

# Add path to Linux PATH var
os.environ['PATH'] = os.environ['PATH'] + f':{os.environ["HOME"]}/bin'

# Copy dlim to new path dir
os.makedirs(f'os.environ['HOME']/bin')
shutil.copyfile(f'os.environ['HOME']/dlim', f'os.environ['HOME']/bin')
```

### Usage

You will need to pass two authentication-related arguments to all `dlim` commands: 
- `--rest-server`: takes the form `https://<wmla-console>/dlim/v1`, where `wmla-console` is for your specific WMLA instance; an example value would be `https://wmla-console-cpd-wmla.apps.cpd.mskcc.org/dlim/v1/`
- `--jwt-token`: CPD bearer authentication token. In a Watson Studio JupyterLab environment, you can use the environment variable `USER_ACCESS_TOKEN`. Otherwise, you can refer to https://cloud.ibm.com/apidocs/cloud-pak-data#getauthorizationtoken.

```python
import os
REST_SERVER = `https://wmla-console-cpd-wmla.apps.cpd.mskcc.org/dlim/v1/`

# Run in JupyterLab
!dlim <args> --rest-server REST_SERVER --jwt-token os.environ['USER_ACCESS_TOKEN']
```

A full list of commands can be seen by running `dlim --help`.

## Deployments

### Preparation

To deploy a model on WMLA, you must first prepare the files that configure the deployment and define the behavior of associated inference tasks. Some [files are mandatory to WMLA](https://www.ibm.com/docs/en/wmla/2.3?topic=inference-create-service), while others are supplementary and depend on the necessities of your model to be deployed. The files are saved to a local directory for submission, then transferred to WMLA via `dlim`, during which this local folder gets compressed and passed over. Once the deployment is up and running, the content of this submission folder is available in the path given by the environment variable `REDHARE_MODEL_PATH`.

__Required files__

These files must be included in the submission folder, or you will receive an error message.

- **Kernel Python file** - This file is a driver that loads the model and defines inference behavior. It makes use of a custom class that defines 3 primary methods defining behavior: `on_kernal_start`, `on_task_invoke`, and `on_kernel_shutdown`. You can read more about creating kernel files for WMLA by visiting the [documentation](https//www.ibm.com/docs/en/wmla/2.3?topic=service-create-kernel-file). In general:
  - `on_kernel_start`: It defines what occurs additionally duirng the startup of a kernel pod, and the kernel will not be ready until the code in this section completes execution. You may consider to use it for installing additional python packages, downloading model files, or initializing models in preparation for inference requests. 
  - `on_task_invoke`: It defines what occurs when an actual request comes through. This usually involves parsing the payload, sending the input data to the loaded model to generate predictions, and returning the response to the user. 
  - `on_kernel_shutdown`: It defines what occurs when the kernel is going to be terminated, most often because of auto-scaling.
- **Model config JSON file** (`model.json`) - Defines general information about the deployment, such as the name of your deployment and that of the kernel file. You can also define custom environment variables. See this [doc page](https://www.ibm.com/docs/en/wmla/2.3?topic=inference-create-service) for more details.
- **README file** (`README.md`) - A markdown file used for documentation to summarize the behavior of your kernel file and define payload inputs and repsonse output. The file entry is required but the content does not have an impact to your deployment.

__Supplementary files__

You may have additional dependency files that are specific to the model deployment, or more precisely, to the inference code in the kernel script. For example, it could be a custom module/package. 

### Creating a deployment

Once your files are contained within a submission folder, you can submit the deployment request using the following command, where `<submission dir>` is the path to directory containing the dependencies:

```python
# Submitting deployment request from JupyterLab
!dlim model deploy -p <submission dir> --rest-server REST_SERVER --jwt-token $USER_ACCESS_TOKEN
```

There is a limit to the amount of data that can be submitted upon deployment (the size of the submission folder), so you may consider transffring the model files to the depoyment environment in other ways, for example downloading model weight files from within the kernel, especially if your model file(s) is considerably large (>1GB). 

### Interacting with active deployments

Note that the following can also be performed from within the WMLA console iteself with a few exceptions:
- You have access to fewer software/hardware config options from the UI
- You cannot undeploy models from the UI

#### Starting and stopping a deployment

After the deployment is created, the status of it is `stopped`. While a deployment is in `stopped` status, you are able to modify configurations such as the resources needed, and the modification will take effect the next time you start this deployment. You also need to stop a deployment before you can delete it using the `dlim model undeploy` command.

To start a deployment:

```python
# Force stop a deployment with -f argument to avoid STDIN interaction
!dlim model start <deploy name> -f --rest-server REST_SERVER --jwt-token $USER_ACCESS_TOKEN
```

To stop a deployment:

```python
# Force stop a deployment with -f argument to avoid STDIN interaction
!dlim model stop <deploy name> -f --rest-server REST_SERVER --jwt-token $USER_ACCESS_TOKEN
```

#### Editing configuration for a deployment

The model JSON file initially supplied when you create a deployment only configures basic settings. To configure settings that allow dynamic modifications after the deployment is created (e.g., resource usage such as to enable GPUs, increase CPU/memory limits, etc.), edit the configuration profile using `dlim`:

1. Stop the deployment
```
dlim model stop -f <deploy name>
```
2. Download the effective configuration JSON file (a.k.a. model profile) from WMLA
```
dlim model viewprofile <deploy name> -j
```
3. Edit this file as you wish
4. Upload the updated model profile
```
dlim model updateprofile <deploy name> -f <path to updated JSON>
```
Refer to this [doc page](https://www.ibm.com/docs/en/wmla/2.3?topic=inference-edit-service) for available config parameters.

An example of steps 1-4:

```python
# Stop the model
!dlim model stop toy-deploy -f --rest-server REST_SERVER --jwt-token $USER_ACCESS_TOKEN

# Download the current config file
!dlim model viewprofile toy-deploy -j --rest-server REST_SERVER --jwt-token $USER_ACCESS_TOKEN > <path to deploy dir>/update_model.json

# Edit the file
with open("<path to deploy dir>/update_model.json",'r') as f:
    update_model = json.load(f)
## Enable GPU usage
update_model['kernel']['gpu'] = 'exclusive'
## Save changes back to JSON file
with open("<path to deploy dir>/update_model.json",'w') as f:
    json.dump(update_model, f)

# Update deployment
!dlim model updateprofile toy-deploy -f <path to deploy dir>/update_model.json --rest-server REST_SERVER --jwt-token $USER_ACCESS_TOKEN
```

#### Deleting a deployment

To delete your deployment, simply undeploy it after it is stopped.

```python
# Force undeploy a deployment with -f argument to avoid STDIN interaction
!dlim model undeploy <deploy name> -f --rest-server REST_SERVER --jwt-token $USER_ACCESS_TOKEN
```

### Additional Information

#### Endpoint for inference requests

The endpoint URL always takes the form `https://<wmla console>/dlim/v1/inference/<deploy name>`. If the deployment name is `toy-deploy`, the REST API endpoint will be `https://wmla-inference-cpd-wmla.apps.cpd.mskcc.org/dlim/v1/inference/toy-deploy` for inference requets to be submitted.

#### Usage of GPU in WMLA EDI
For memory-intensive GPU-based inference, it is recommended to use the `exclusive` strategy (set the `gpu` parameter to `exclusive`), which allows only 1 request to be processed at a time within a kernel pod. As of WMLA 2.3.5 (CPD 4.0.5), WMLA EDI allocates a maximum of 1 GPU per kernel pod.

The `resources` parameter takes a string that defines the CPU and memory settings. The string takes the form `ncpus=<a>,ncpus_limit=<b>,mem=<c>,mem_limit=<d>`. It basically contains 2 pairs:
- `ncpus` and `mem`: these two values are effective for "exclusive" strategy
- `ncpus_limit` and `mem_limit`: these two values are effective for "shared" strategy (the GPU-packing feature in EDI)
However, even when strategy "exclusive" is used, it is still recommended that you set the right limit in `ncpus_limit` and `mem_limit` (for example, use the same value in `ncpus` and in `ncpus_limit`). 

