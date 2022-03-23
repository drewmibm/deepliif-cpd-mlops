# Description of deployment pipeline notebook

The **A2_WMLA_Deploy.ipynb** notebook automates model deployment on WMLA, and runs as part of the MLOps flow as indicated in [Instructions_MLOps.md](Instructions_MLOps.md). The interaction with WMLA Elastic Distributed Inference (EDI) service is done through the EDI CLI (`dlim`).

This notebook can be executed automatically via the `deploy` command available in the MLOps CLI tool `cli_mlops.py`, or as part of [A_MLOps_Pipeline.ipynb](../A_MLOps_Pipeline.ipynb) when running the MLOps flow interactively. Either way, the general steps of the deployment notebook include:

1. Read user-supplied environment variables
2. Read deployment metadata YML containing WMLA deployment configs
3. Download dependencies from WML deployment space required for WMLA deployment submission
4. Deploy the model and configure advanced settings
5. Test deployment and inference service

## To complete before executing the deployment pipeline notebook

As described in [Instructions_MLOps.md](Instructions_MLOps.md), a few steps are assumed completed before the deployment pipeline notebook is executed:

- Trained model file(s) uploaded to the WML space
- Model-specific file dependencies for WMLA uploaded to the WML space (typically including a kernel file `kernel.py` and a readme file `README.md` as required by WMLA, and any model-specific code required for running inference tasks)
- Configuration of deployment added to the yaml file in the WML space 
- Essential environment variables already set up

The above steps should be completed after you followed [A_MLOps_Pipeline.ipynb](../A_MLOps_Pipeline.ipynb). If you use the MLOps CLI (`cli_mlops.py`), the `stage` command takes care of all the above except for the last one, which is covered in the `deploy` command.

Additional information about the input used is summarized in the following table:

| source | requirement | value/field | description |
|-------------|--------|-------------|-------------|
| environment variable | deployment space id | WML_SPACE_ID | id of WML deployment space containing staged model files and dependencies |
|| model asset id | MODEL_ASSET_ID | id of trained model asset in deployment space <br> same as key of relevant deployment metadata YML entry |
|| CPD username | CPD_USERNAME | CPD username for authentication |
|| CPD api key | CPD_API_KEY | CPD api key for authentication |
|| rest server | REST_SERVER | Required by dlim CLI tool; takes form https://\<your-wmla-console\>/dlim/v1/ |
|| path to dlim | DLIM_PATH | Local path to dlim CLI tool |
|| kernel filename | KERNEL_FILENAME | Name of WMLA kernel file, default to 'kernel.py' |
| deployment yml | deployment name | \<yml\>.wmla_deployment.deployment_name | name to assign deployment in WMLA |
|| model-specific dependency filename |\<yml\>.wmla_deployment.dependency_filename| name of zip file on WML deployment space |
|| trained model file |\<yml\>.model_asset| name of zip file on WML space |
|| resource configs |\<yml\>.wmla_deployment.resource_configs| software/hardware configs |

## Step by Step Description

### 1. Read user-supplied environment variables

These environment variables are required for the pipeline notebok to run properly. They carry information that either is required to locate the relevant deployment configuration (in `deployment_metadata.yml`), or is not supposed to be included in the yml configuration such as secrets.

### 2. Read deployment metadata YML containing WMLA deployment configs

The deployment metadata YML contains information required to complete model deployment on WMLA. Relevant fields are assigned to local variables that are used in deployment configuration later in the notebook.

### 3. Download dependencies from WML deployment space required for WMLA deployment submission

WMLA EDI CLI (`dlim`) requires submission of a directory containing needed files in order to create a deployment (the EDI API takes an archive instead). In this pipeline, only the **dependency asset** is passed over in this step. The **model asset** at this moment is downloaded into the deployment environment when the environment is starting, as specified in the kernel file. 

This submission directory is dynamically created with the staged archives downloaded from the WML deployment space, including:
- `DEPLOY_DEPENDENCY_FILE` is the zipped up model-specific dependency asset containing files needed by WMLA EDI as well as those needed by the inference code. The name of this asset is fetched from the deployment metadata configuration YML. 
- `general_dependencies` is a hard coded list of general utility scripts that are useful across deployments. 

In addition, a file named `model.json` will be automatically generated using the provided information and placed under the submission folder. Details about this file can be found in this [doc page](https://www.ibm.com/docs/en/wmla/2.3?topic=inference-create-service).

### 4. Deploy the model and configure advanced settings

Configuration of advanced settings as specified in the `resource_configs` section of the deployment metadata YML file occurs after a model is initially deployed. After downloading the JSON file containing the current confifuration profile associated with the deployment, its contents are updated with those specified in `resource_configs` and the deployment profile is then updated. At this point, the inference service is ready to be started.

### 5. Test deployment and inference service

The deployment pipeline notebook is embedded with checks to ensure that the deployment and inference service is properly and successfully set up.
