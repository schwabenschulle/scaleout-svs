### SVS

### Prepare runner
virtualenv --python python3.6 cobra_3.6
source cobra_3.6/bin/activate
pip install -r requierments.txt

Update APIC IP in XLS

### Start script ADD
python scaleout_2022.py -ipg -p -leaf

### Delete
python scaleout_2022.py -dl -dipg -dp