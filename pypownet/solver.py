import os
from pyomo.opt import SolverFactory
from pyomo.core import Var
from pyomo.core import Param
from operator import itemgetter
import pandas as pd
from datetime import datetime
import pyomo.environ as pyo
from model import PowerNetPyomoModelCambodian


def solve_powernet(pownet_pyomo, solver='glpk', year=2016, start_day=1, last_day=365):
    """
    simulation year, start(1-365) and end(1-365) days of simulation
    """
    model = pownet_pyomo.create_model()
    model_data_path = pownet_pyomo.get_data_path()
    print(model_data_path)
    #model_data_path = 'temp.dat'
    instance = model.create_instance(model_data_path)


    ######=================================================########
    ######               Segment C.4                       ########
    ######=================================================########

    ###solver and number of threads to use for simulation
    opt = SolverFactory("glpk") #SolverFactory("gurobi") ##SolverFactory("cplex")
    #opt.options["threads"] = 1
    H = instance.HorizonHours
    K = range(1, H+1)


    ######=================================================########
    ######               Segment C.5                       ########
    ######=================================================########

    ###Run simulation and save outputs

    #Space to store results
    on=[]
    switch=[]

    mwh=[]
    hydro=[]
    solar=[]
    wind=[]

    hydro_import=[]

    srsv=[]
    nrsv=[]

    vlt_angle=[]

    for day in range(start_day, last_day+1):
        if hasattr(instance, 'd_nodes'):
            for z in instance.d_nodes:
                # Load Demand and Reserve time series data
                for i in K:
                    instance.HorizonDemand[z, i] = instance.SimDemand[z, (day-1)*24+i]
                    instance.HorizonReserves[i] = instance.SimReserves[(day-1)*24+i] 
                
        if hasattr(instance, 'h_nodes'):
            for z in instance.h_nodes:
                # Load Hydropower time series data
                for i in K:
                    instance.HorizonHydro[z, i] = instance.SimHydro[z, (day-1)*24+i]
                
        if hasattr(instance, 's_nodes'):
            for z in instance.s_nodes:
                # Load Solar time series data
                for i in K:
                    instance.HorizonSolar[z, i] = instance.SimSolar[z, (day-1)*24+i]
                
        if hasattr(instance, 'w_nodes'):
            for z in instance.w_nodes:
                # Load Wind time series data
                for i in K:
                    instance.HorizonWind[z, i] = instance.SimWind[z, (day-1)*24+i]
                
        if hasattr(instance, 'h_imports'):
            for z in instance.h_imports:
                # Load Hydropower time series data
                for i in K:
                    instance.HorizonHydroImport[z,i] = instance.SimHydroImport[z,(day-1)*24+i]     
        
        result = opt.solve(instance) ##,tee=True to check number of variables
        # instance.display()
        instance.solutions.load_from(result)   
    
        #The following section is for storing and sorting results
        for v in instance.component_objects(Var, active=True):
            varobject = getattr(instance, str(v))
            a = str(v)
            if a=='hydro':      
                for index in varobject:
                    if int(index[1]>0 and index[1]<25):
                        if index[0] in instance.h_nodes:
                            hydro.append((index[0],index[1]+((day-1)*24),varobject[index].value))   

            elif a=='solar':
                for index in varobject:
                    if int(index[1]>0 and index[1]<25):
                        if index[0] in instance.s_nodes:
                            solar.append((index[0],index[1]+((day-1)*24),varobject[index].value))   

            elif a=='wind':
                for index in varobject:
                    if int(index[1]>0 and index[1]<25):
                        if index[0] in instance.w_nodes:
                            wind.append((index[0],index[1]+((day-1)*24),varobject[index].value))   

            elif a=='hydro_import':      
                for index in varobject:
                    if int(index[1]>0 and index[1]<25):
                        if index[0] in instance.h_imports:
                            hydro_import.append((index[0],index[1]+((day-1)*24),varobject[index].value))   

            elif a=='vlt_angle':
                for index in varobject:
                    if int(index[1]>0 and index[1]<25):
                        if index[0] in instance.nodes:
                            vlt_angle.append((index[0],index[1]+((day-1)*24),varobject[index].value))   

            elif a=='mwh':  
                for index in varobject:
                    if int(index[1]>0 and index[1]<25):
                        mwh.append((index[0],index[1]+((day-1)*24),varobject[index].value))                            

            elif a=='on':       
                ini_on_ = {}  
                for index in varobject:
                    if int(index[1]>0 and index[1]<25):
                        on.append((index[0],index[1]+((day-1)*24),varobject[index].value))
                    if int(index[1])==24:
                        ini_on_[index[0]] = varobject[index].value    

            elif a=='switch':  
                for index in varobject:
                    if int(index[1]>0 and index[1]<25):
                        switch.append((index[0],index[1]+((day-1)*24),varobject[index].value))

            elif a=='srsv':    
                for index in varobject:
                    if int(index[1]>0 and index[1]<25):
                        srsv.append((index[0],index[1]+((day-1)*24),varobject[index].value))
                            
            elif a=='nrsv':   
                for index in varobject:
                    if int(index[1]>0 and index[1]<25):
                        nrsv.append((index[0],index[1]+((day-1)*24),varobject[index].value))                             
        
        # Update initialization values for "on" 
        for z in instance.Generators:
            instance.ini_on[z] = round(ini_on_[z])
        
        print(day)
        print(str(datetime.now()))

    return {
        'on': on,
        'switch': switch, 
        'mwh': mwh,
        'hydro': hydro, 
        'solar': solar, 
        'wind': wind, 
        'hydro_import': hydro_import, 
        'srsv': srsv, 
        'nrsv': nrsv, 
        'vlt_angle': vlt_angle
    }


def save_node_result(soln_data, out_csv_fpath, cols):
    #Save outputs to csv files
    soln_pd = pd.DataFrame(soln_data, columns=cols)
    soln_pd.to_csv(out_csv_fpath)


if __name__ == "__main__":
    run_no = 1
    year = 2016
    pownet_pyomo = PowerNetPyomoModelCambodian(year=year)
    solns = solve_powernet(pownet_pyomo, solver='glpk', year=year, start_day=1, last_day=4)
    for soln_node in solns:
        csv_path = f'out_camb_R{run_no}_{year}_{soln_node}.csv'
        if soln_node in ['hydro', 'hydro_import', 'solar', 'wind', 'vlt_angle']:
            save_node_result(solns[soln_node], csv_path, ('Node','Time','Value'))
        elif soln_node in ['mwh', 'on', 'switch', 'srsv', 'nrsv']:
            save_node_result(solns[soln_node], csv_path, ('Generator','Time','Value'))
        else:
            save_node_result(solns[soln_node], csv_path, ('Node','Time','Value'))