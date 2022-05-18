# Instructions for Custom Monitors
OpenScale comes with a few out-of-the-box (OOTB) monitors, including:
- Quality
- Fairness
- Drift
Each monitor contains multiple metrics that measures the performance of interest over time, and one monitor can be applied onto multiple deployments to be tracked.

In addition to the OOTB monitors, it is helpful to create **custom monitors** that are tailored to the context and could be re-used by model deployments of a similar kind. For example, a monitor for image segmentation metrics.


## 1. Terminology
A few important concepts in OpenScale:

#### Subscription
In order for OpenScale to monitor a model deployment, a **subscription** is created that tells information such as the id of the deployment, what monitors to use, etc.

#### Integrated System / Custom Metric(s) Provider
A custom configuration for OpenScale to use and invoke an endpoint that calculates metrics. It contains information such as the scoring url and how to authenticate.

#### Monitor Definition
A **monitor definition** on high-level tells what metrics are included and their default values. Definition of a monitor can possibly include tens or more metrics. In some sense, it is similar to a statement saying "in my monitor _xyz_ let's say there is a metric called _abc_, the higher the better, and usually a value below 0.6 would be concerning".

#### Monitor Instance (per subscription)
Whenever a **monitor definition** is needed by a subscription, a **monitor instance** gets created that is specific to the target **subscription**. In this way, thresholds can be configured for different subscriptions & status can differ, while still using the same **monitor definition** framework.

When creating a monitor instance, Once a **monitor definition** is associated with an **integrated system**, OpenScale will be able to automatically invoke metric computation requests if this monitor definition is used in a model deployment monitored by OpenScale (a.k.a. a **subscription**).

For a **monitor instance** using a custom **monitor definition**, it is optional to provide an **integrated system** against which OpenScale could request and collect calculated metrics. Without an associated **integrated system**, OpenScale has no way to compute these custom metrics and expects the metrics to be logged programmatically via the metrics logging api.


## 2. Procedures
The ultimate goal when developing a custom monitor is to get a rest API registered to OpenScale, so that OpenScale can invoke this endpoint periodically and log the metrics. Technically, this means
- a deployment is needed for each custom monitor, in order to have a rest API endpoint
- the deployment does the following:
  - selectively loads the data
  - calculates the metrics
  - triggers OpenScale's metric logging method

Watson Machine Learning (WML) can be used to host a deployment. The instructions here are tailored to WML, though the main idea can be applied to deployments hosted elsewhere.

To define the deployment, WML accepts a so-called python deployable function, or a script as an extention to a function. You can find the structure of such a script in this [doc page](https://www.ibm.com/docs/en/cloud-paks/cp-data/4.0?topic=functions-writing-deployable-python).

Note:  
space: Watson Machine Learning deployment space

### 2.1 Develop Custom Monitor Script
This script defines how each metric of a custom monitor is computed. An example in the form of a function can be found here: [OpenScale Tutorial](https://github.com/IBM/watson-openscale-samples/blob/main/Cloud%20Pak%20for%20Data/WML/notebooks/custom_metrics/Custom%20Metrics%20Provider%20for%20Cloud%20Pak%20for%20Data.ipynb) (see the custom metric provider function)

In the context of a deployable script, note that:
1. The final function to be called has to have the name `score`.
2. If you wish to examine the WML deployment environment as the function `get_metrics()` runs, inspect it by inserting logging etc. within this function. The local files created by this function will be gone if you inspect the environment from function `score()`. 
   For example:
       def get_metrics(subscription_id):
           ...
           cmds = ['ls -lh']
           d_log = {}
           for cmd in cmds:
               d_log[cmd] = subprocess.check_output(cmd,shell=True).decode()
           return d_log
           
       def score(input_data):
           ...
           return {'predictions':[{'values':[[get_metrics(subscription_id)]]}]}
   Alternatively, you can change the function name. Change `get_metrics()` to `score()`, and give `score()` another name, so that the deployment endpoint will execute the code in `get_metrics()` (now the new `score`) and return the infromation you need.
   
#### How to handle dependencies?
If it's necessary to bring in dependent python variables or scripts (e.g., a utility script), here is an example:
```
import wml_sdk_utils as wml_util

path_custom_metrics_script = 'custom_metrics_segmentation.py'

variables = {"os.environ['RUNTIME_ENV_APSX_URL']":os.environ['RUNTIME_ENV_APSX_URL'],
             "os.environ['USERNAME']":'<username>',
             "os.environ['APIKEY']":'<apikey>',
             'space_id':'<space id>'}

scripts = ['wml_sdk_utils.py']

wml_util.function_prepare(path_custom_metrics_script,variables,scripts)
```
This utility function inserts the defined variables in to the main deployable script. For scripts, it writes the content of each script as a string into the deployable script, and comes with a piece of code to write these strings back to the "local" directory as a python script with the same name when being executed. 

As a result, for the above example, in the deployable script you can directly call variable `space_id` or `os.environ['USERNAME']`, and import the depdent script by `from wml_sdk_utils import *`.

This utility function creates a modified version of the supplied deployable script, with suffix `_edited`: if the original script is named `myscript.py`, the modified script will be `myscript_edited.py`.

Remember to deploy this modified script, not the original script.

*Having the credentials as additional variables added using the utility function is useful when you need to version control the custom monitor script, say using github. You don't want to take the risk of leaking your credentials to github, but still want to keep track of the changes. Using this method, you can track the original custom monitor script, and locally test & deploy the modified one.*

### 2.2 Local Test
You may refer to notebook [B1_OpenScale_Custom_Monitor_Dev_and_Test](../B1_OpenScale_Custom_Monitor_Dev_and_Test.ipynb) that shows how to add dependent variables & scripts into a custom monitor deployale script, and then run local testing, or use the following examples.

#### Test code outside of functions
```
exec(open('<path to script>','r').read())
```

#### Test code in the key function for metric calculation: `get_metrics()`
```
exec(open('<path to script>','r').read())
get_metrics(subscription_id='')
```
You may need to supply the needed information to the required argument(s).

#### Full test of the score function?
Unfortunately, this is **impossible**. The reason is that the `score` function requires input that you do not have at the moment of developing a custom monitor: subscription id, monitor id, monitor instance id, integrated system id .... OpenScale needs to pass in such information to trigger metrics logging when this custom monitor is used in reality.

### 2.3 Deploy Script
You may refer to notebook [B2_OpenScale_Custom_Monitor_Deploy](../B2_OpenScale_Custom_Monitor_Deployment.ipynb). Basically it covers the following tasks:

| step | input | output |
|------|-------|--------|
|1. create a WML online deployment | custom monitor deployable script | deployment id <br> scoring url |
|2. register the custom metric provider in openscale | scoring url | integrated system id |
|3. create the corresponding monitor definition | config of default thresholds | monitor id |
|4. update monitor metadata | monitor id <br> integrated system id <br> deployment id | new/updated entry in monitor yml |
