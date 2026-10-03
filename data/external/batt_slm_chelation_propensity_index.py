import os
import sys
import numpy as np
from pathlib import Path

CPI_DIR = Path("your_own_path/CPI")

# directory of the intermediate files
INPUT_DIR = CPI_DIR / "Input"
if not os.path.exists(INPUT_DIR):
    os.mkdir(INPUT_DIR)

# for BOLTZMANN average
BOLTZMANN_CONSTANT = 0.0019872041  # k, kcal/mol/K
TEMPERATURE = 298.15  # temperature, (K)

#
def gen_mol_feature_files():

    smiles = []
    titles = []
    lines = []
    with open(CPI_DIR / "SolvFunc-87.csv", "r") as f:
        lines = f.readlines()
        titles = lines[0].strip("\n").split(";")
        smiles_col = titles.index("SMILES")
        smiles = [l.strip("\n").split(";")[smiles_col] for l in lines[1:]]

    from rdkit import Chem
    from rdkit.Chem import AllChem,rdFreeSASA,rdMolTransforms,rdmolops

    # get energy optimized 3D structure
    params = AllChem.ETKDGv3()
    params.numThreads = 0
    params.randomSeed = 999
    params.useBasicKnowledge = True
    params.useExpTorsionAnglePrefs = True
    params.useMacrocyclesTorsions = True
    params.useSmallRingTorsions = True
    params.useRandomCoords = True
    params.useMachineLearning = True

    # Bondi A. (1964) J. Phys. Chem. 68:441-451
    # J. Phys. Chem. A 2009, 113, 19, 5806–5812, DOI(10.1021/jp8111556)
    bondi_radii = {
        1: 1.20,   # H
        6: 1.70,   # C
        7: 1.55,   # N
        8: 1.52,   # O
        9: 1.47,   # F
        15: 1.80,  # P
        16: 1.80,  # S
        17: 1.75,  # Cl
    }

    # for Li: 1.82 for std. vdw, 1.81 for Bondi radius
    # J. Phys. Chem. A 2009, 113, 19, 5806–5812, DOI(10.1021/jp8111556)
    sasa_opt = rdFreeSASA.SASAOpts()
    sasa_opt.probeRadius = 1.81

    electronegative_atoms = ["N", "O"]
    print(electronegative_atoms)

    # output
    result_file = INPUT_DIR / "Features.csv"
    if os.path.exists(result_file):
        os.remove(result_file)

    with open(result_file, "w") as g:

        new_title = lines[0].strip() + ";SASA(O/N,max);Num(13O);Num(14O);Num(15O)\n"
        g.write(new_title)

        for mol_index in range(0, len(smiles)):

            print(mol_index)
            mol_with_hydrogen = Chem.AddHs(Chem.MolFromSmiles(smiles[mol_index]))

            origin_line = lines[mol_index+1].strip()

            # generate confomers
            pot_eners = []
            keep_cid = []
            try:
                cids = AllChem.EmbedMultipleConfs(mol_with_hydrogen, 50, params)
                props = AllChem.MMFFGetMoleculeProperties(mol_with_hydrogen)
                for cid_index in range(0, len(cids)):
                    AllChem.MMFFOptimizeMolecule(mol_with_hydrogen, confId=cids[cid_index]) # optimization is necessary
                    potential = AllChem.MMFFGetMoleculeForceField(mol_with_hydrogen, props, confId=cids[cid_index])
                    pot_eners.append(potential.CalcEnergy()) # kcal/mol
                    keep_cid.append(cids[cid_index])
            except:
                origin_line += ";99;99;99;99\n"
                g.write(origin_line)
                continue

            # calculate the BOLTZMANN weight
            energies = np.array(pot_eners)
            min_energy = np.min(energies)
            relative_energies = energies - min_energy
            boltzmann_factors = np.exp(-relative_energies / (BOLTZMANN_CONSTANT * TEMPERATURE))
            weights = boltzmann_factors / np.sum(boltzmann_factors)

            # Adjusted radii are needed, otherwise the probe atom will touch the molecules with a distance of zero
            sasa_for_confs = [0.0] * len(keep_cid)
            adjusted_radii = [bondi_radii[atom.GetAtomicNum()] + sasa_opt.probeRadius for atom in mol_with_hydrogen.GetAtoms()]
            for cid_index in range(0, len(keep_cid)):
                sasa_for_atoms = []
                # https://f1000research.com/articles/5-189/v1, unit = Ang^2
                rdFreeSASA.CalcSASA(mol_with_hydrogen, confIdx=keep_cid[cid_index], radii=adjusted_radii, opts=sasa_opt)
                for atom_index in range(0, len(mol_with_hydrogen.GetAtoms())):
                    symbol = mol_with_hydrogen.GetAtomWithIdx(atom_index).GetSymbol()
                    if symbol not in electronegative_atoms:
                        continue
                    sasa_for_atoms.append(float(mol_with_hydrogen.GetAtomWithIdx(atom_index).GetProp("SASA")))
                if len(sasa_for_atoms) > 0:
                    sasa_for_confs[cid_index] = np.max(sasa_for_atoms)
            sasa_for_confs = np.array(sasa_for_confs)

            # compute the potential to form Chelating structure with Li+
            # ACS Energy Lett. 2025, 10, 4962−4982, five-membered ring or six-membered ring
            num_1_3_O_pair = [0.0] * len(keep_cid)
            num_1_4_O_pair = [0.0] * len(keep_cid)
            num_1_5_O_pair = [0.0] * len(keep_cid)
            for cid_index in range(0, len(keep_cid)):
                coordinated_atom_index = []
                rdFreeSASA.CalcSASA(mol_with_hydrogen, confIdx=keep_cid[cid_index], radii=adjusted_radii, opts=sasa_opt)
                for atom in mol_with_hydrogen.GetAtoms():
                    sasa_value = float(atom.GetProp("SASA"))
                    symbol = atom.GetSymbol()
                    if symbol in electronegative_atoms and sasa_value > 0.5:
                        coordinated_atom_index.append(atom.GetIdx())
                if len(coordinated_atom_index) < 2:
                    continue

                for i in range(0, len(coordinated_atom_index)):
                    idx1 = coordinated_atom_index[i]
                    for j in range(i + 1, len(coordinated_atom_index)):
                        idx2 = coordinated_atom_index[j]
                        # two atoms in ring can not form Chelation with Li+
                        if mol_with_hydrogen.GetAtomWithIdx(idx1).IsInRing() or mol_with_hydrogen.GetAtomWithIdx(idx2).IsInRing():
                            continue
                        # for circles with 5/6 elements, d(1，3-DOL) = 2.34, d(1,3-DX) = 2.36m, d(DME,max)=3.63
                        dist = rdMolTransforms.GetBondLength(mol_with_hydrogen.GetConformer(keep_cid[cid_index]), idx1, idx2)
                        if dist > 4.0:
                            continue
                        # check the path between two atoms, OC(O)(O) group also can form chelation
                        path = rdmolops.GetShortestPath(mol_with_hydrogen, idx1, idx2)
                        if len(path) == 3:
                            num_1_3_O_pair[cid_index] += 1
                        elif len(path) == 4:
                            num_1_4_O_pair[cid_index] += 1
                        elif len(path) == 5:
                            num_1_5_O_pair[cid_index] += 1

            num_1_3_O_pair = np.array(num_1_3_O_pair)
            num_1_4_O_pair = np.array(num_1_4_O_pair)
            num_1_5_O_pair = np.array(num_1_5_O_pair)

            # combine scores of componenets
            assert len(sasa_for_confs) == len(num_1_3_O_pair) == len(num_1_4_O_pair) ==len(num_1_5_O_pair)

            # average over confomers with boltzmann weight
            mol_average_sasa = float(np.average(sasa_for_confs, axis=0, weights=weights))
            mol_average_13oxygen_pair = float(np.average(num_1_3_O_pair, axis=0, weights=weights))
            mol_average_14oxygen_pair = float(np.average(num_1_4_O_pair, axis=0, weights=weights))
            mol_average_15oxygen_pair = float(np.average(num_1_5_O_pair, axis=0, weights=weights))

            origin_line += ";%f;%f;%f;%f\n"%(mol_average_sasa,mol_average_13oxygen_pair, mol_average_14oxygen_pair,mol_average_15oxygen_pair)
            g.write(origin_line)

    # get feature files for molecules without F
    gen_mol_feature_files_no_fluorine ()

# 
def gen_mol_feature_files_no_fluorine ():

    smiles = []
    titles = []
    lines = []
    with open(INPUT_DIR / "Features.csv") as f:
        lines = f.readlines()
        titles = lines[0].strip("\n").split(";")
        smiles_col = titles.index("SMILES")
        smiles = [l.strip("\n").split(";")[smiles_col] for l in lines[1:]]

    with open(INPUT_DIR / "Features-NoF.csv", "w") as g:
        g.writelines(lines[0])
        for mol_index in range(0, len(smiles)):
            if "F" in smiles[mol_index]:
                continue
            g.writelines(lines[mol_index+1])

# CDE: class 1; WSE: class 0
def train_logistic_classifer():

    model_name = "LogR-CPI"

    model_dir = CPI_DIR / model_name
    if not os.path.exists(model_dir):
        os.mkdir(model_dir)

    # change the standard output file
    result_file = model_dir / "result.txt"
    result_file = open(result_file, "w")
    old_std_out = sys.stdout
    sys.stdout = result_file

    # get features of molecular
    mol_id = []
    raw_features = []
    raw_data = []
    raw_label = []
    with open(INPUT_DIR / "Features-NoF.csv") as g:

        lines = g.readlines()
        titles = lines[0].strip("\n").split(";")

        id_col = titles.index("Abbreviation")
        function_col = titles.index("Function")
        sasa_col = titles.index("SASA(O/N,max)")

        raw_features = titles[sasa_col:]
        for mol_index in range(0, len(lines[1:])):
            line_index = mol_index + 1
            items = lines[line_index].strip("\n").replace(",", ".").split(";")
            mol_id.append(items[id_col].split("(")[0])
            raw_data.append(items[sasa_col:])
            function_class = 1 # related to the solvating power, so set label = 1 for CDE
            if "WSE" in items[function_col]:
                function_class = 0
            raw_label.append(function_class)

    raw_features = np.array(raw_features)
    raw_data = np.array(raw_data).astype(np.float64)
    raw_label = np.array(raw_label).astype(np.float64)

    # normalized by the averaged values
    print("Features =", raw_features)
    feature_mean = np.mean(raw_data, axis=0)
    print("Feature mean values before normalized = ", feature_mean) # [62.828, 0.482, 0.139, 0.015]
    raw_data = raw_data / feature_mean
    feature_mean = np.mean(raw_data, axis=0)
    print("Feature mean values after normalized = ", feature_mean)

    # use 0.5 as the binary classification point
    print("Num of WSE = ", len(np.where(raw_label < 0.5)[0]))
    print("Num of CDE = ", len(np.where(raw_label > 0.5)[0]))

    # constrain the coefficient > 0.0
    from scipy.optimize import minimize
    from sklearn.metrics import log_loss # Cross-Entropy Loss
    from sklearn.preprocessing import add_dummy_feature

    # to deal with the extremely large/negative values for original sigmoid
    # def sigmoid(z):
    #     result = np.zeros_like(z)
    #     mask = z >= 0
    #     result[mask] = 1 / (1 + np.exp(-z[mask]))
    #     mask = z < 0
    #     result[mask] = np.exp(z[mask]) / (1 + np.exp(z[mask]))
    #     return result

    def logistic_loss(params, X, y):
        w = params  # params: intercept and coef
        z = X @ w  # linear combination : z = w0 + w1*x1 + ... + wn*xn
        y_pred = 1 / (1 + np.exp(-z))  # Predicted probabilities p(y=1|x), original Sigmoid
        margin_penalty = 30.0 * np.mean(np.maximum(0, 1 - y * z)) # maximal the marge, see SVM
        return log_loss(y, y_pred)+margin_penalty

    raw_data_bias = add_dummy_feature(raw_data) # add bias before the first column

    # the coefficients should be positive
    # fitting on whole dataset, because of the size of dataset is small and we expected the CPI can completely seperate the current WSE and CDEs
    init_params = [1.0,1.0,1.0,1.0,1.0]
    constraints = [{'type': 'ineq', 'fun': lambda params: params[i]} for i in range(1, raw_data_bias.shape[1])]
    classifier = minimize(fun=logistic_loss, x0=init_params, args=(raw_data_bias, raw_label),
                       constraints=constraints, method='SLSQP')
    intercept = classifier.x[0]
    coeffs = classifier.x[1:]

    # modify the coeff and intercept to scale the predictions within 0 - 1
    formula = ""
    for index in range(0, len(raw_features)):
        formula += "(%.3f)*(%s)+"%(coeffs[index], raw_features[index])
    formula += "(%.3f)"%(intercept)

    origin_pred = []
    for mol_index in range(0, len(mol_id)):
        temp_formula = formula
        for feature_index in range(0, len(raw_features)):
            temp_formula = temp_formula.replace(f"({raw_features[feature_index]})",
                                                  f"({raw_data[mol_index][feature_index]})")
        origin_pred.append(eval(temp_formula))

    # shift to 0
    origin_pred = np.array(origin_pred)
    intercept = intercept - np.min(origin_pred)
    origin_pred = origin_pred - np.min(origin_pred)
    # scale to 0-1
    intercept /= np.max(origin_pred)
    coeffs /= np.max(origin_pred)

    print("-------------------coefficient and intercept_----------------")
    final_formula = ""
    for index in range(0, len(raw_features)):
        final_formula += "(%.3f)*(%s)+"%(coeffs[index], raw_features[index])
    final_formula += "(%.3f)"%(intercept)
    print(final_formula)

    # reset std out
    sys.stdout.flush()
    sys.stdout = old_std_out
    result_file.close()

#
def predict_cpi():

    # change it manully, and the input_file should be including the delta E
    input_file_name = "Features-NoF"
    input_file = INPUT_DIR / f"{input_file_name}.csv"
    if not os.path.exists(input_file):
        raise ValueError(f"No input_file were found")
    
    model_name = "LogR-CPI"
    model_dir = CPI_DIR / model_name
    if not os.path.exists(model_dir):
        raise ValueError(f"No models {model_name} were found")

    raw_features = []
    raw_data = []
    raw_label = []
    input_lines = []
    with open(input_file, "r") as g:

        input_lines = g.readlines()
        titles = input_lines[0].strip("\n").split(";")

        function_col = titles.index("Function")
        sasa_col = titles.index("SASA(O/N,max)")

        raw_features = titles[sasa_col:]
        for mol_index in range(0, len(input_lines[1:])):
            line_index = mol_index + 1
            items = input_lines[line_index].strip("\n").split(";")
            raw_data.append(items[sasa_col:])
            function_class = 1
            if "WSE" in items[function_col]:
                function_class = 0
            raw_label.append(function_class)

    raw_features = np.array(raw_features)
    raw_data = np.array(raw_data).astype(np.float64)
    raw_label = np.array(raw_label).astype(np.float64)

    # normalized by the averaged values
    print("Features =", raw_features)
    feature_mean = []
    with open(model_dir / "result.txt", "r") as f:
        lines = f.readlines()
        assert "Feature mean values before normalized =" in lines[1]
        feature_mean = lines[1].split("=")[1].strip(" []\n").split()
        feature_mean = np.array(feature_mean, dtype=np.float32)

    print("Feature mean values before normalized = ", feature_mean)
    raw_data = raw_data / feature_mean
    feature_mean = np.mean(raw_data, axis=0)
    print("Feature mean values after normalized = ", feature_mean)

    final_formula = ""
    with open(model_dir / "result.txt", "r") as f:
        lines = f.readlines()
        is_formula_start = False
        for line in lines:
            if "coefficient and intercept" in line:
                is_formula_start = True
                continue
            if is_formula_start:
                final_formula = line.strip(" \n+")
                is_formula_start = False
                break
    print(final_formula)

    # output
    with open(model_dir / f"{input_file_name}-predictions.csv", "w") as g:

        g.write("%s;CPI\n"%(input_lines[0].strip("\n")))
        for mol_index in range(0, len(raw_label)):
            temp_formula = final_formula
            for feature_index in range(0, len(raw_features)):
                temp_formula = temp_formula.replace(f"({raw_features[feature_index]})", f"({raw_data[mol_index][feature_index]})")
            g.write("%s;%f\n"%(input_lines[mol_index+1].strip("\n"), eval(temp_formula)))

# 
if __name__ == "__main__":

    # gen_mol_feature_files()

    # train_logistic_classifer()

    predict_cpi()

