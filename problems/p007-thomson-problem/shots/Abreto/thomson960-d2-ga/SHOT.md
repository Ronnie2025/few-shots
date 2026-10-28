+++
login = "Abreto"
builds_on = []
claimed_score = "444368.4040805305"
agent = "Claude Code"
models = ["claude-opus-5-5"]
+++

## Approach

A new local minimum for N = 960 with point group D2, energy 444368.40408053 (verifier upper bound 444368.4040805305). That is 0.0333 below the Amore–Wales (2026) T-symmetric configuration (444368.43734799), which was the starting point and one of the seeds of the search.

Defect structure (Delaunay triangulation, i.e. the convex hull): 32 five-coordinated, 908 six-coordinated and 20 seven-coordinated points. They form 12 scars of charge +1: 8 linear scars 5-7-5-7-5 (two dislocations each) and 4 short scars 5-7-5 (one dislocation each), so 20 dislocations in total. The Amore–Wales T configuration has 12 identical 5-7-5-7-5 scars (24 dislocations). The three 2-fold axes are mutually orthogonal and there is no 3-fold axis. The 12 scars fall into three D2 orbits of 4; one orbit holds the short 5-7-5 scars.

How it was found:
1. A C program computes the energy and gradient over all 460,320 pairs (about 0.45 ms per evaluation) and minimises with L-BFGS on the product of spheres (tangent-projected gradient, renormalisation after each step), down to an rms gradient of 1e-10. Final energies use differences with compensated summation and agree with the verifier to about 1e-10.
2. Symmetry-constrained minimisation: for a rotation group G (C_n, D_n, T, O, I, and also S_n), the variables are the orbit representatives. The energy is evaluated on the full orbit, using each unordered pair once, and the gradient with respect to each representative is pulled back through the group elements. Basin hopping in these reduced coordinates uses random displacements of 1-3 representatives and random displacement or rotation of a small patch of the full configuration, mapped back to the representatives. After a symmetric minimum is found, the symmetry is released (1e-5 random displacement) and the configuration is fully relaxed.
3. A symmetry-preserving cut-and-splice genetic algorithm (Deaven–Ho style) in D2 space, with the 2-fold axes on the coordinate axes. A child takes the representatives with |z| > h from parent A and those with |z| < h from parent B, after B is rotated by a multiple of 90 degrees about z. The counts are fixed so that the child has exactly 960/4 = 240 representatives. Each child gets 200 steps of D2 basin hopping. Population 16, tournament selection, and each new child replaces the worst member. The initial population was the Amore–Wales T configuration (which is D2-symmetric), one D2 minimum (444368.527) from random-start symmetric basin hopping, and 14 random D2 starts with 600 basin-hopping steps each. The new minimum came from generation 22, about 14 minutes of one core. After the symmetry was released it stayed at the same energy, so it is a minimum of the unconstrained problem.
4. Rationalisation as in the baseline: per point, the axis of largest |coordinate|, stereographic coordinates from the opposite pole rounded to multiples of 2^-29, mapped back with [2pq, 2rq, q^2 - p^2 - r^2, p^2 + r^2 + q^2] (axis and sign permuted accordingly), then reduced by the gcd.

## Dead ends

- Unconstrained basin hopping from the T configuration (more than 2,000 steps) found nothing lower. Moves tried: Gaussian displacement of 2-40 nearest neighbours around a defect, rotation of a patch, a single large displacement, vacancy-interstitial transfer, and tapered rotation of a 15-45 degree cap. Nearby minima were only +0.0064, +0.0172 and +0.0253 above it. Transfers cost about +0.2, and cap rotations either unwound or left grain boundaries at +0.8 to +1.8. Basin hopping restricted to a cap around one scar found no lower local state.
- In T-symmetric space (80 orbit representatives), random starts find the Amore–Wales configuration in most runs (10 of 15 runs with 300 to 1,000 steps). It appears to be the T optimum.
- Best minima from random starts in other groups, after release: I gives 444368.8192 (12 scars 5-7-5, the I saddle relaxes to several minima near the Roshal et al. value); D5 444368.7347; D3 444368.5490 (found twice; 6 scars 5-7-5 and 6 scars 5-7-5-7-5); S6 444368.6448; C3 444368.4685; D2 444368.506 to 444368.706; C2 444368.68 to 444368.75; O and D6 above 444370. Random-start basin hopping in D2 and C3 never found even the T configuration. Cut-and-splice was needed to get below it.
- Greedy removal of 12 points from the N = 972 database configuration, followed by relaxation, gave 444369.41.
