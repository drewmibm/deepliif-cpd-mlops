# MLOps

This MLOps flow starts from the stage when researchers / data scientists finished training the model and testing the deployment, and shared their model file(s), deployment script, and configurations for deployment & monitor to the MLOps team.

## 1. Preparation
Make sure the researchers / data scientists provided the following items before you can proceed:
- [ ] Model file(s), a folder or a file
- [ ] Deployment folder, including:
  - [ ] Main deployment script a.k.a. kernel file
  - [ ] Readme.md (if there is not, you can create one; it's required by WMLA EDI but has no impact)
  - [ ] (Optional) Other dependencies
- [ ] Deployment settings, including:
  - [ ] Deployment name
  - [ ] Resources config, for example:
```
{'enable_gpus':'True',
 'n_cpus':8,
 'memory_allocation':10000,
 'n_replicas':1,
 'n_min_kernels':1,
 'task_execution_timeout':2*60}
```

- [ ] Monitor settings, including:
  - [ ] Monitor name / id
  - [ ] Monitor configuration
    - [ ] (Optional) Information needed by specific monitor
    - [ ] Thresholds, for example:
```
THRESHOLDS_SEGMENTATION = {'precision': {'threshold': [60.0, 'lower']},
 'precision_positive': {'threshold': [0.6, 'lower']},
 'precision_negative': {'threshold': [0.6, 'lower']},
 'recall': {'threshold': [15.0, 'lower']},
 'recall_positive': {'threshold': [0.15, 'lower']},
 'recall_negative': {'threshold': [0.15, 'lower']},
 'f1': {'threshold': [45.0, 'lower']},
 'f1_positive': {'threshold': [0.45, 'lower']},
 'f1_negative': {'threshold': [0.45, 'lower']},
 'Dice': {'threshold': [20.0, 'lower']},
 'Dice_positive': {'threshold': [0.20, 'lower']},
 'Dice_negative': {'threshold': [0.20, 'lower']},
 'IOU': {'threshold': [12.0, 'lower']},
 'IOU_positive': {'threshold': [0.12, 'lower']},
 'IOU_negative': {'threshold': [0.12, 'lower']},
 'PixAcc': {'threshold': [35.0, 'lower']},
 'PixAcc_positive': {'threshold': [0.35, 'lower']},
 'PixAcc_negative': {'threshold': [0.35, 'lower']}}
```

You can fill in the information you gathered in the User Configuration section, and then follow the notebook [A_MLOps_Pipeline](A_MLOps_Pipeline.ipynb) to generate a deployment metadata yaml file. Alternative, you may refer to the example yaml [deployment_metadata_cli_example.yml](deployment_metadata_cli_example.yml) and ask researchers / data scientists to provide you with a deployment metadata yaml of the same structure.

#### How to make my yaml based on the example?
You can create a copy of the example and make modifications.
- ignore the fields with null value as they will be filled automatically during the MLOps process
- ignore the main key "MODEL_ASSET_ID" - yes it will be auto-filled too :)
- mainly what needs to be configured are:
  1. deployment configuration, such as how much memory is needed, etc.
  2. monitor configuration, such as the threshold for each metric under each monitor
    - you need to delete the unwanted monitor from the example and add your preferred one(s) if they are not already there
    - refer to [section 3.3](https://github.com/drewmibm/deepliif-cpd-mlops#33-thresholds_-metric-thresholds-for-openscale-monitor) to see how to get all metrics and their default thresholds
    

## 2. Procedures
You can either use the cli tool [cli_mlops.py](cli_mlops.py), or follow the notebook for more interactive experience [A_MLOps_Pipeline](A_MLOps_Pipeline.ipynb). It's recommended to use the cli as it provides more functionalities.

Note:  
space: Watson Machine Learning deployment space

### 2.1 CLI
The cli is more or less a wrapper of notebook [A_MLOps_Pipeline](A_MLOps_Pipeline.ipynb) with more functionalities. 

A list of example commands can be found in [cheat_sheet_cli_mlops.txt](docs/cheat_sheet_cli_mlops.txt)

#### 1. Prepare the environment
Make sure you have CPD access token and WML space id as environment variable. Check using the following command:
```
echo $USER_ACCESS_TOKEN
echo $SPACE_ID
```

Configure if not specified:
```
export SPACE_ID=<wml space id to stage files to>
```

In addition, your `dlim` tool (WMLA's CLI for EDI inference service) needs to be in a place registered to `$PATH`. For example, if the `dlim` file is in folder `/userfs`, register this folder to `$PATH` by running:
```
export PATH=$PATH:/userfs
```

#### How to get CPD access token?
To get a token, refer to https://cloud.ibm.com/apidocs/cloud-pak-data#getauthorizationtoken or use the `get_access_token()` method in `cpd_utils.py`.

#### How to get `dlim`?
You can download it from [WMLA web console](https://wmla-console-cpd-wmla.apps.cpd.mskcc.org/ui/#/cliTools). Note that as of CPD 4.0.5, **it automatically selects the architecture that matches the system where you browser sits**. If you use a windows machine to open this page, the downloaded `dlim` will be for windows and cannot be used in a linux environment.

#### 2. Stage the model and dependency files, along with the config
You will see model asset id printed out that you may need for steps afterwards..
```
python cli_mlops.py prepare stage --path-model <path to model file(s)> --path-dependency <path to dependency file(s)> --path-yml <path to config yml>
```

For example:
```
python cli_mlops.py prepare stage --path-model=/mnts/AdditionalDeepLIIFVolume/deepliif-ws-output/Test_Model_wendy_ws_serialized2 --path-dependency=/userfs/wmla-deployment/edi-deployment-dirs/deepliif-base --path-yml=/userfs/deployment_metadata_cli_example.yml
```


#### 3. Deploy the model
Similar to how this notebook works, the `deploy create` method at the backend executes pipeline notebook [A2](A2_WMLA_Model_Deploy.ipynb).
```
python cli_mlops.py deploy create --name <deployment name> --model-asset-id <model asset id>
```
Additional optional parameters:
- `kernel-filename`: filename of the kernel script, default to `kernel.py`
- `custom-arg`: key-value pairs to be inserted into the kernel script on the fly, good to store changeable variables or credentials (so the kernel script in git repository doesn't contain sensitive information)
- `save-notebook`: whether to save the executed notebook

For example:
```
python cli_mlops.py deploy create --name my-model --model-asset-id 41a9a8ff-dcaa-4f0f-beb5-2e1bbaa2f384 --kernel-filename kernel.py --custom-arg CPD_USERNAME=***** --custom-arg CPD_API_KEY=********** --custom-arg VOLUME_DISPLAY_NAME=AdditionalDeepLIIFVolume
```

#### 4. Configure monitors for the model
Similar to how this notebook works, the `monitor create` method at the backend executes pipeline notebook [A3_OpenScale_Configuration](A3_OpenScale_Configuration.ipynb).
```
python cli_mlops.py monitor create --name <deployment name> --service-provider-name <openscale deployment service provider name> --save-notebook <True to save the executed pipeline notebook out>
```
Additional optional parameters:
- `service_provider_name`: OpenScale service provider name to register the deployment from, default to a headless service provider named `OpenScale Headless Service Provider`
- `save-notebook`: whether to save the executed notebook

For example:
```
python cli_mlops.py monitor create --name deepliif-wendy
```


#### How to get the latest monitor status for a deployment?
This method retrieves back the information of the latest evaluation for each of the monitors configured with your deployment.
```
python cli_mlops.py monitor status --name <deployment name>
```

For example:
```
python cli_mlops.py monitor-status --name deepliif-wendy
```


### 2.2 MLOps Notebook

#### Main Notebook to Run
The main notebook is the entry point to the configuration and execution of pipeline notebooks.

| notebook | step | input | output |
|----------|------|-------|--------|
| A_MLOps_Pipeline | 1. Create draft deployment yml | user config | user config variables <br> updated python str `metadata` |
|                  | 2. Add needed assets (e.g., model files) to space| `PATH_MODEL` (user config) <br> `PATH_DEPENDENCY` (user config) | assets in space, including model asset id |
|                  | 3. Create final deployment yml | python str `metadata` <br> model asset id <br> user config variables | python dict `metadata` | 
|                  | 3. Add deployment yml to space | python dict `metadata` | updated `deployment_metadata.yml` in space |
|                  | 4. Kick off pipeline notebooks, for each of the notebooks | python list `paths_nb` | cell output <br> (optional) copy of executed pipeline notebook |
|                  | 4.1 Specify needed input as environment variables, if not in yml | ... | env vars used by a pipeline notebook|
|                  | 4.2 Execute pipeline notebook | | |

#### Pipeline Notebooks
The training notebook is not technically a part of the pipeline, as this is expected to be handled by the researchers / data scientists. If needed, it can be converted to a pipeline notebook.

| notebook | step | input | output | note |
|----------|------|-------|--------|------|
| A1_Submit_WMLA_Training | 1. Configure training: <br> - scripts and dependencies <br> - config of training env (e.g., number of gpus) | | | |
|                         | 2. Prepare submission folder | `paths_file` and `paths_folder` (user config) | a submission folder with all scripts and dependencies | for `distPyTorch`, an additional snippet of code is needed in the main script |
|                         | 3. Submit training | submission folder | | | |

If necessary, all the user config that are not part of the deployment metadata yaml file can be moved into it. 

| notebook | step | input / read from yml | output / write to yml |
|----------|------|-----------------------|-----------------------|
| A2_ | | | |
| A3_OpenScale_Configuration | 1. Get deployment service provider | `os.environ['SERVICE_PROVIDER_NAME']` | `SERVICE_PROVIDER_ID` |
|                            | 2. Create new subscription | `SERVICE_PROVIDER_ID` <br> `os.environ['SUBSCRIPTION_NAME']` | `SUBSCRIPTION_ID` |
|                            | 3. Update deployment yml | | `openscale_subscription_id` (deployment yml) |
|                            | 4. Create monitor instances | `openscale_custom_metric_provider` (deployment yml) <br> `integrated_system_id` (monitor yml) | |
|                            | 5. (Optional) Manual evaluation run | | |



## 3. User Configuration
Here lists a few tricky fields to find a value for:

### 3.1 `WML_SPACE_ID`: WML Deployment Space ID
You need to first decide which WML deployment space to use. Then, you can find the space id either from the UI (Deployments -> <your deployment space> -> Manage -> General -> Space GUID), or programmatically as the follows:
```
import wml_sdk_utils as wml_util
wml_client = wml_util.get_client()
wml_client.spaces.list(limit=100)
```

### 3.2 `SERVICE_PROVIDER_NAME`: Deployment Provider in OpenScale Monitor
For WMLA deployments, you can use a headless provider, meaning that it provides dummy information and is not technically linked to a real service that handles deployments. 

This is because 
1. WMLA is not an out-of-the-box deployment provider supported in OpenScale
2. The custom monitors we have at the moment (`segmentation_metrics` and `generic_metrics`) monitors the ground truth images & predicted images in a storage volume, and do **not** require OpenScale to interact with a deployment endpoint.

You can view all the available deployment provider already registered in OpenScale, and get the name of the provider you wish to use:
```
import wos_sdk_utils as wos_util
wos_client = wos_util.get_client()
wos_client.service_providers.show()
```

If you need to create a new headless deployment provider, follow notebook [C1_OpenScale_Dummy_ML_Provider.ipynb](C1_OpenScale_Dummy_ML_Provider.ipynb)

### 3.3 `THRESHOLDS_<>`: Metric Thresholds for OpenScale Monitor
Get default monitor thresholds:
```
import wos_sdk_utils as wos_util
wos_client = wos_util.get_client()

thresholds_segmentation = wos_util.get_default_thresholds('segmentation_metrics',wos_client)
thresholds_generic = wos_util.get_default_thresholds('generic_metrics',wos_client)
```

You may programmatically change the threshold of specific metric in a monitor:
```
# modify thresholds for your subscription/deployment
thresholds_generic['num_images_recent_ground_truth']['threshold'][0] = 100
thresholds_generic['num_images_recent_predicted']['threshold'][0] = 800

thresholds_segmentation['Dice']['threshold'][0] = 20
thresholds_segmentation['Dice_positive']['threshold'][0] = 0.2
thresholds_segmentation['Dice_negative']['threshold'][0] = 0.2
thresholds_segmentation['IOU']['threshold'][0] = 12
thresholds_segmentation['IOU_positive']['threshold'][0] = 0.12
thresholds_segmentation['IOU_negative']['threshold'][0] = 0.12
```

Or, copy and paste the output of the thresholds object (a python dictionary), and modify the values accordingly.
```
thresholds_segmentation = {'precision': {'threshold': [60.0, 'lower']},
 'precision_positive': {'threshold': [0.6, 'lower']},
 'precision_negative': {'threshold': [0.6, 'lower']},
 'recall': {'threshold': [15.0, 'lower']},
 'recall_positive': {'threshold': [0.15, 'lower']},
 'recall_negative': {'threshold': [0.15, 'lower']},
 'f1': {'threshold': [45.0, 'lower']},
 'f1_positive': {'threshold': [0.45, 'lower']},
 'f1_negative': {'threshold': [0.45, 'lower']},
 'Dice': {'threshold': [20.0, 'lower']},
 'Dice_positive': {'threshold': [0.20, 'lower']},
 'Dice_negative': {'threshold': [0.20, 'lower']},
 'IOU': {'threshold': [12.0, 'lower']},
 'IOU_positive': {'threshold': [0.12, 'lower']},
 'IOU_negative': {'threshold': [0.12, 'lower']},
 'PixAcc': {'threshold': [35.0, 'lower']},
 'PixAcc_positive': {'threshold': [0.35, 'lower']},
 'PixAcc_negative': {'threshold': [0.35, 'lower']}}
```
    
### 3.4 Modify Metadata
In the metadata, you need to add value for `openscale_custom_metric_provider` according to the monitor configuration you received / planned. The value to field `openscale_custom_metric_provider` is a dictionary, with key representing monitor id (e.g., segmentation_metrics) and value another dictionary depicting various configurations. For example, if only `generic_metrics` is needed, the entry may look like the following:
```
'openscale_custom_metric_provider': {'generic_metrics': {'dir_gt': 'DeepLIIF_Datasets/model_eval/gt_images',
   'dir_pred': 'DeepLIIF_Datasets/model_eval/model_images',
   'most_recent': 1,
   'thresholds': {'num_images_recent_ground_truth': {'threshold': [5.0,
      'lower']},
    'num_images_recent_predicted': {'threshold': [40.0, 'lower']},
    'num_images_total_ground_truth': {'threshold': [5.0, 'lower']},
    'num_images_total_predicted': {'threshold': [40.0, 'lower']}},
   'volume_display_name': 'AdditionalDeepLIIFVolume'}}
```

Instead of inserting the value of configurations directly like the above, you may also change the template in the notebook that uses python variables to fill in the string, and then intepret the string into a metadata python dictionary. Note that in the template you need to **use double brackets to indicate a single bracket**, in order for python to differentiate a real bracket character from a bracket used for reference to a python variable.
    

## 4. Fetch Monitor Status Manually
Use the following code snippet to fetch monitor status.

```
import wos_sdk_utils as wos_util
wos_client = wos_util.get_client()
```

#### Custom monitors
```
from ibm_watson_openscale.supporting_classes.enums import TargetTypes
wos_client.monitor_instances.measurements.query(target_id=<subscription id>,
                                                target_type=TargetTypes.SUBSCRIPTION,
                                                monitor_definition_id=<monitor id>,
                                                recent_count=1).result.to_dict()
```

#### OOTB monitors
Get monitor instance id and run id:
```
wos_util.get_monitor_instance(<monitor id>,<subscription id>,wos_client)
```

Get run details:
```
wos_client.monitor_instances.get_run_details(monitor_instance_id=<monitor instance id>,
                                             monitoring_run_id=<run id>)
```

Alternatively, you can list all the runs of a monitor instance:
```
wos_client.monitor_instances.list_runs(monitor_instance_id=<monitor instance id>).result.to_dict()
```

