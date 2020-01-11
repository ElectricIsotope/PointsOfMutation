# TODO: 'numpyify' graph for fast forward prop
#               batch out numpified functions and return fitness from evaluator pods
#               can use a shared queue or manager that sends results back to a genepool pod and genomes (numpy array ops) to game pods
#               since evaluation environments and distribution dont fit easily into a dask/spark pipeline
# TODO: use numpy with recarray for forward propagation and partition into respective ndarray matrix for each
#              layer with weights, signals and isActivated entries respectively

from nodeGene import nodeGene as node
from connectionGene import connectionGene as connection
import random as rand
from activationFunctions import softmax


class genome:
    # NOTE: graphs are defined by their Node objects not Connections. Node defined networks
    # allow for more interesting encapsulation and swappable implementations as well as make
    #  recurrent, energy based etc. networks easier to implement. Connection defined topologies are skipped
    #  in favor of a 'numpifier' which compiles the traced network down to a series of almost if not
    # entirely numpy operations. This network is not lightweight nor ideal for real time forward propagation
    #  but prefered  for ease of crossover, mutability etc. (relatively low frequency operations) and high level
    #  exploration of network topologies. The graph executor would preferably be written in the numpy C API
    #  but this development should be empirically justified.
    '''
    a genome built with fully connected initial topology

    Parameters:
        inputSize: integer size of input nodes
        outputSize: integer size of output nodes
        globalConnections: list of all connections to keep things consistent
        nodeId: current highest nodeId counter for keeping globalConnections
    Constructs:
        a fully connected topology of given input and output dimensions with random initial weights
    '''

    def __init__(self, inputSize, outputSize, globalConnections):
        self.inputNodes = []
        self.outputNodes = []
        self.hiddenNodes = []
        self.fitness = 0
        nodeId = 0

        for newNode in range(0, inputSize):
            nodeId += 1
            self.inputNodes.append(node(nodeId))

        for outNode in range(0, outputSize):
            nodeId += 1
            self.outputNodes.append(node(nodeId))

        for inNode in self.inputNodes:
            for outNode in self.outputNodes:
                globalConnections.verifyConnection(connection(
                    rand.uniform(-1, 1), inNode, outNode))
        # prevents calculating after the fact and 'somewhat' less messy
        globalConnections.nodeId = nodeId

    def addNodeMutation(self, nodeMutationRate, globalConnections):
        '''
        randomly adds a node, if successful returns the innovation adjustment for global innovation counter
        '''
        if rand.uniform(0, 1) > nodeMutationRate:
            randNode = rand.choice(
                self.hiddenNodes + self.outputNodes+self.inputNodes)
            if randNode in self.hiddenNodes:
                if rand.uniform(0, 1) > 0.5:
                    randConnection = rand.choice(randNode.outConnections)
                else:
                    randConnection = rand.choice(randNode.inConnections)
            elif randNode in self.outputNodes:
                randConnection = rand.choice(randNode.inConnections)
            elif randNode in self.inputNodes:
                randConnection = rand.choice(randNode.outConnections)

            self.addNode(randConnection, globalConnections)

    def addConnectionMutation(self, connectionMutationRate, globalConnections):
        '''
        randomly adds a connection connections to input and from output nodes are allowed (circularity at all nodes)
        '''
        # NOTE: num nodes^2 is number of possible connections before depleted conventions.
        #             so long as self connections and recurrent connections (but no parallel connections)
        #             are allowed
        if rand.uniform(0, 1) > connectionMutationRate:
            allNodes = self.hiddenNodes+self.outputNodes+self.inputNodes
            newConnection = connection(
                rand.uniform(-1, 1), rand.choice(allNodes), rand.choice(allNodes))
            self.addConnection(newConnection, globalConnections)

    def addConnection(self, newConnection, globalConnections):
        '''
        add a unique connection into the network attaching two nodes, self connections and recurrent connections are allowed

        Checks if a connection already exists locally (prevents parallel edges) or globally (innovation consistency).
        also checks if a connection creates a loop closure and marks it as recurrent.
        '''
        allNodes = self.hiddenNodes+self.outputNodes+self.inputNodes
        for checkNode in allNodes:
            # TODO: the sum of these lists ~doubles the search space with repeats make this a set or unique
            if newConnection.exists(checkNode.outConnections + checkNode.inConnections) == True:
                    # TODO: this clips mutation rates probability distribution for cases:
                    #              connectionMutationRate>>nodeMutationRate and very small, sparse networks
                    #               instead check if numConnections = allNodes**2
                print('mutation Failed: already in this genome')
                print(newConnection.input.nodeId,
                      newConnection.output.nodeId)
                del newConnection
                return

        newConnection = globalConnections.verifyConnection(newConnection)
        print('new connection acquired')
        print(newConnection.input.nodeId,
              newConnection.output.nodeId)

        # Check simple recurrence
        # TODO: EXTRACT THIS INTO ANOTHER METHOD
        if newConnection.input == newConnection.output:
            newConnection.loop = True
            return
        elif newConnection.input in self.inputNodes and newConnection.output in self.inputNodes:
            newConnection.loop = True
            return
        elif newConnection.output in self.outputNodes and newConnection.input in self.outputNodes:
            newConnection.loop = True
            return
        # is this a case? Should still be caught since connection would remain unactivated
        # elif newConnection.input in self.outputNodes and newConnection.output in self.inputNodes:
        #     newConnection.loop = True
        #     return
        else:
            # TODO: this can be partly encapsulated in nodeGene just like forward propagation wrt .activate()
            # Forward propagate this connection. if outputs are arrived at it is not recursive.
            # if this connection's input node is found along the search it is. ignore all known loops
            # TODO: BROKEN HERE somehow missing a loop detection and looping a loop external to newConnection on search
            #               This does not handle an output to an output. must propagate the entire network
            #                doesnt cycle but gets stuck in unready state
            connectionBuffer = []
            seenOnce = False  # TODO: This is a hack but is only working version
            # TODO: use activate as a way to note if a node has been seen
            # NOTE: ENSURE ALL NODES ARE PROPERLY DEACTIVATED HERE AND FORWARD PROP
            connectionList = [
                x for x in newConnection.output.outConnections if x.loop == False]
            while len(connectionList) > 0:
                print('IN LOOP CHECK: step.')
                for nextConnection in connectionList:
                    # let this connection search path die off since its already a known loop
                    if nextConnection.loop == False:
                        print('IN LOOP CHECK: appending..',
                              len(connectionBuffer))

                        nextConnection.input.activated = True
                        # TODO: shouldnt have to track activation if loops are consistently detected.
                        connectionBuffer += [
                            x for x in nextConnection.output.outConnections if x not in connectionBuffer and x.loop == False]
                    else:
                        print('SKIPPING A LOOP CONNECTION')
                        pass
                # lookahead at all nodes to see if they have been activated
                for checkConnection in connectionBuffer:
                    if checkConnection.output.activated == True:
                        print('IN LOOP CHECK: LOOP DISCOVERED FOR: ',
                              newConnection.input.nodeId, newConnection.output.nodeId)
                        newConnection.loop = True
                        # Reset all connections because its easier
                        for processedNode in self.hiddenNodes + self.outputNodes + self.inputNodes:
                            processedNode.activated = False
                        return

                connectionList.clear()
                connectionList.extend(connectionBuffer)
                print(len(connectionList))
                connectionBuffer.clear()

            for processedNode in self.hiddenNodes + self.outputNodes + self.inputNodes:
                processedNode.activated = False

        print('done')

    def addNode(self, replaceConnection, globalConnections):
        '''
        adds a node into the network by splitting a connection into two connections adjoined by the new node
        '''
        # We are splitting replaceConnection
        replaceConnection.disabled = True
        # check innovation of the two new connections and ensure loop considerations are maintained
        newNode = globalConnections.verifyNode(
            replaceConnection.input, replaceConnection.output, replaceConnection.loop)
        print('newNode', newNode)
        # add this genome
        self.hiddenNodes.append(newNode)

    # TODO: encapsulate the 3 states (input hidden output) to nodegene.activate to make code here a
    #              simple loop call, this will segue to parallelization better. CURRENTLY BROKEN HERE

    def forwardProp(self, signals):
        '''
        propagate a list of signals through the network.

        Throws an error if input matrix doesnt match input node matrix of network.
        Parameters:
            signals: a list of signals to be passed through of len inputNodes
        Returns:
            signals: a list of signals to be sent to outputs of len outputNodes
        '''
        assert len(signals) == len(self.inputNodes), "Mismatch input matrix Signals: {}, Input Nodes: {}".format(
            len(signals), len(self.inputNodes))

        unfiredNeurons = []
        nextNeurons = []
        outputs = []
        ###########INITIALIZE INPUT SIGNALS###########
        # TODO: need to handle loop and self connections in input and output state
        for sig, inputNode in zip(signals, self.inputNodes):
            for initialConnection in inputNode.outConnections:
                if initialConnection.disabled is True:
                    pass
                else:
                    initialConnection.signal = softmax(
                        sig)  # called statically for input
                    print('SIGTRACE (init): ', initialConnection.signal,
                          ' * ', initialConnection.weight)
                    # ensure its not an input to output connection
                    # (which wont need further forward propagation)
                    if len(initialConnection.output.outConnections) > 0:
                        unfiredNeurons.append(initialConnection.output)

        ###########PROCESS HIDDEN LAYER###########
        # begin forward proping
        # TODO: this only loops forever when a loop is missed in connectionGene creation
        while True:
            for processingNode in unfiredNeurons:

                # print('DEBUG: type of processingNode is: ', processingNode)
                activating = processingNode.activate()
                # TODO: this should never happen as same state is asserted in nodeGene.activate()
                if activating is None:
                    assert "ERROR: IMPOSIBLE STATE IN FORWARD PROPAGATION"
                    pass
                # TODO: cycling here
                if activating is not None:
                    if type(activating) is not list:
                        activating = [activating]
                    nextNeurons.extend(activating)

            if len(nextNeurons) > 0:
                # print('DEBUG: next propagation nodes: ', nextNeurons)
                print(nextNeurons, unfiredNeurons)
                unfiredNeurons.clear()
                unfiredNeurons.extend(nextNeurons)
                print('now: ', unfiredNeurons)
                print('DEBUG: Processing {} unfiredNeurons'.format(
                    len(unfiredNeurons)), unfiredNeurons)
                nextNeurons.clear()
            else:
                break

        ###########ACQUIRE OUTPUT SIGNALS###########
        # TODO: recurrent connections across output nodes causes errors here. need to rely further on encapsulated
        # nodeGene.activate() method
        # have to manually activate output just as with input since special FSM case
        for finalNode in self.outputNodes:
            finalSignal = 0
            for finalConnection in finalNode.inConnections:
                if finalConnection.disabled is True:
                    print('Disabled SIGTRACE (final): ', finalConnection.signal,
                          ' * ', finalConnection.weight)
                    if finalConnection.loop is True:
                        print('Loop SIGTRACE (final): ',
                              finalConnection.signal, finalConnection.weight)
                    # pass
                elif finalConnection.signal is None:
                    print('NULL SIGTRACE (final): ',
                          finalConnection.signal, finalConnection.weight)
                    if finalConnection.loop is True:
                        print('Loop SIGTRACE (final): ',
                              finalConnection.signal, finalConnection.weight)
                else:
                    # print('SIGTRACE(final): ', finalConnection.signal,
                    #       finalConnection.weight)
                    finalSignal += finalConnection.signal * finalConnection.weight
                    # if finalConnection.disabled:
                    # else:
                    print('SIGTRACE (final): ', finalConnection.signal,
                          ' * ', finalConnection.weight)

                # print('SIGTRACE (final): ', softmax(finalSignal),
                #   ' * ', finalConnection.weight)
            outputs.append(softmax(finalSignal))
        # Reset nodes
        for processedNode in self.hiddenNodes + self.inputNodes + self.outputNodes:
            processedNode.activated = False
        return outputs
