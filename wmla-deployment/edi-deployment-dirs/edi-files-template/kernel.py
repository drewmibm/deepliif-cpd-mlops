#!/usr/bin/env python

import redhareapiversion
from redhareapi import Kernel
import json
import traceback


class MatchKernel(Kernel):
    
    def on_kernel_start(self, kernel_context):
       pass
        
    def on_task_invoke(self, task_context):
        try:
            while task_context != None:
                input_data = json.loads(task_context.get_input_data())
                
                # request tasks go here

                output_data = {} # output dictionary for request
                task_context.set_output_data(json.dumps(output_data))
                task_context = task_context.next()
                    
           
        except Exception as e:
            traceback.print_exc()
            Kernel.log_error(f"Failed due to {str(e)}")
    
    def on_kernel_shutdown(self):
        pass

        
if __name__ == '__main__':
    obj_kernel = MatchKernel()
    obj_kernel.run()
