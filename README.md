# PowNet Refactored
![license MIT](https://img.shields.io/github/license/kamal0013/PowNet) 

# PyPowNet: A Python Library for PowNet Model Optimization
[PowNet](https://github.com/kamal0013/PowNet/) is a least-cost optimization model for simulating the Unit Commitment and Economic Dispatch of large-scale power systems.
It has been applied to model Cambodian, Laotian, and Thai power systems.
PyPowNet improves the original implementation of PowNet and simplifies the model specification process.
It aims to help researchers to import their own power system data on the PowNet model and and serve as a benchmark for optimization solvers.
Ultimately, we hope that our effort will encourage more regions to adopt renewable energy sources in the power system.

# Requirements
PyPowNet is written in Python 3.6. It requires the following Python packages: (i) Pyomo, (ii) NumPy, and (iii) Pandas. It also requires an optimization solver (e.g. CPLEX). 
PyPowNet has been tested in Anaconda on Windows 10.

# Installation
You can perform a minimal install of ``pypownet`` with:

.. code:: shell

    git clone https://github.com/pacowong/pypownet.git
    cd pypownet
    pip install -e .

# How to run
```python
python pypownet/solver.py datasets/kamal0013/camb_2016 2016 1 2 1 glpk
```
If you have installed [glpk], this will execute the model using the data on Cambodian power system.
The script also generates .csv files containing the values of each decision variable.

# Citation
If you use PyPowNet for your research, please cite the following papers:

```bibtex
@article{chowdhury2020pownet,
  title={{PowNet: A Network-Constrained Unit Commitment/Economic Dispatch Model for Large-Scale Power Systems Analysis}},
  author={Chowdhury, AFM Kamal and Kern, Jordan and Dang, Thanh Duc and Galelli, Stefano},
  journal={Journal of Open Research Software},
  volume={8},
  number={1},
  year={2020},
  publisher={Ubiquity Press}
}
```

```bibtex
@article{chowdhury2020expected,
  title={{Expected Benefits of Laos' Hydropower Development Curbed by Hydroclimatic Variability and Limited Transmission Capacity: Opportunities to Reform}},
  author={Chowdhury, AFM Kamal and Dang, Thanh Duc and Bagchi, Arijit and Galelli, Stefano},
  journal={Journal of Water Resources Planning and Management},
  volume={146},
  number={10},
  pages={05020019},
  year={2020},
  publisher={American Society of Civil Engineers}
}
```

```bibtex
@article{chowdhury2020greater,
  title={{The Greater Mekong's climate-water-energy nexus: how ENSO-triggered regional droughts affect power supply and CO2 emissions}},
  author={Chowdhury, Kamal AFM and Dang, Thanh Duc and Nguyen, Hung TT and Koh, Rachel and Galelli, Stefano},
  journal={Earth and Space Science Open Archive ESSOAr},
  year={2020},
  publisher={American Geophysical Union}
}

```

```bibtex
@misc{pypownet,
    author = {Pak-Kan Wong},
    title = {{PyPowNet: A Python Library for Refactored PowNet Model Optimization}},
    year = {2020},
    publisher = {GitHub},
    journal = {GitHub repository},
    howpublished = {\url{https://github.com/pacowong/pypownet}},
}
```

# License
PyPowNet is released under the MIT license. 
