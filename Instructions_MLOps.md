# Instructions for MLOps

This MLOps flow starts from the stage when researchers / data scientists finished training the model and shared their model file(s) and configurations for deployment & monitor to the MLOps team.

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

You can fill in the information you gathered in the User Configuration section, and then follow the notebook to generate a deployment metadata yaml file. Alternative, you may ask researchers / data scientists to provide you with the deployment metadata yaml directly.

## 2. Procedures

Note:  
space: Watson Machine Learning deployment space

### Main Notebook to Run
The main notebook is the entry point to the configuration and execution of pipeline notebooks.

| notebook | step | input | output |
|----------|------|-------|--------|
| A_MLOps_Pipeline | 1. Create draft deployment yml | user config | user config variables <br> updated python str `metadata` |
|                  | 2. Add needed assets (e.g., model files) to space| `PATHS` (user config) | assets in space, including model asset id |
|                  | 3. Create final deployment yml | python str `metadata` <br> model asset id <br> user config variables | python dict `metadata` | 
|                  | 3. Add deployment yml to space | python dict `metadata` | updated `deployment_metadata.yml` in space |
|                  | 4. Kick off pipeline notebooks, for each of the pipelines | python list `paths_nb` | cell output <br> (optional) copy of executed pipeline notebook |
|                  | 4.1 Specify needed input as environment variables, if not in yml | ... | env vars used by a pipeline notebook|
|                  | 4.2 Execute pipeline notebook | | |

### Pipeline Notebooks
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

If you need to create a new headless deployment provider, follow notebook [C1_OpenScale_Dummy_ML_Provider.ipynb]()

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
