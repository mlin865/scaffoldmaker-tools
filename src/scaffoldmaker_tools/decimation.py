import math
from scaffoldmaker.annotation.annotationgroup import AnnotationGroup, findAnnotationGroupByName, \
    getAnnotationGroupForTerm, findOrCreateAnnotationGroupForTerm
from cmlibs.zinc.context import Context
from cmlibs.zinc.element import Element, Elementbasis
from cmlibs.zinc.field import Field
from cmlibs.zinc.node import Node
from cmlibs.utils.zinc.field import find_or_create_field_coordinates, get_group_list, findOrCreateFieldFiniteElement
from cmlibs.utils.zinc.finiteelement import get_element_node_identifiers


def decimate(filename, targetLength=100):
    """
    A simple function to reduce points in ex file by sampling arclength between junctions into target distance.
    :param filename: file to be decimated.
    :param targetLength: Target arclength between points.
    Return downsampled file
    """
    context = Context("Test")
    region = context.getDefaultRegion()
    tmpRegion = region.createRegion()

    fieldModule = tmpRegion.getFieldmodule()
    coordinates = find_or_create_field_coordinates(fieldModule)
    radius = findOrCreateFieldFiniteElement(fieldModule, 'radius', 1)
    rgb = findOrCreateFieldFiniteElement(fieldModule, 'rgb', 3)

    # Retrieve nodes, elements and groups from original file
    sir = tmpRegion.createStreaminformationRegion()
    sir.createStreamresourceFile(filename)
    tmpRegion.read(sir)

    nodeset = fieldModule.findNodesetByFieldDomainType(Field.DOMAIN_TYPE_NODES)
    mesh1d = fieldModule.findMeshByDimension(1)
    fieldcache = fieldModule.createFieldcache()

    nodeIdList = [[]]
    xList = [[]]
    radiusList = [[]]
    rgbList = [[]]

    nodeIter = nodeset.createNodeiterator()
    node = nodeIter.next()

    fieldcache.setNode(node)
    while node.isValid():
        identifier = node.getIdentifier()
        fieldcache.setNode(node)
        result, x = coordinates.getNodeParameters(fieldcache, -1, Node.VALUE_LABEL_VALUE, 1, 3)
        resultRadius, r = radius.getNodeParameters(fieldcache, -1, Node.VALUE_LABEL_VALUE, 1, 1)
        resultRGB, colour = rgb.getNodeParameters(fieldcache, -1, Node.VALUE_LABEL_VALUE, 1, 3)
        node = nodeIter.next()
        nodeIdList.append(identifier)
        xList.append(x)
        radiusList.append(r)
        rgbList.append(colour)

    elementIter = mesh1d.createElementiterator()
    element = elementIter.next()
    elementList = []

    while element.isValid():
        eft = element.getElementfieldtemplate(coordinates, -1)
        nodeIdentifiers = get_element_node_identifiers(element, eft)
        elementList.append(nodeIdentifiers)
        element = elementIter.next()

    elementGroupsList = [[] for n in range(len(elementList))]
    allGroups = get_group_list(fieldModule)
    for group in allGroups:
        groupName = group.getName()
        meshGroup = group.getMeshGroup(mesh1d)
        elementiter = meshGroup.createElementiterator()
        element = elementiter.next()
        while element.isValid():
            elementIdentifier = element.getIdentifier()
            elementGroupsList[elementIdentifier - 1].append(groupName)
            # eft = element.getElementfieldtemplate(coordinates, -1)
            # node1 = element.getNode(eft, 1)
            # node2 = element.getNode(eft, 2)
            # print(elementIdentifier, node1.getIdentifier(), node2.getIdentifier())
            element = elementiter.next()

    totalNodes = len(xList)

    # Create parent-child list & child-parent list
    childList = []  # stores node numbering of children
    clearedChildList = []  # stores nodes that have been taken care of
    parentList = []  # stores node numbering of parents
    for i in range(1, totalNodes + 2):
        childList.append([0, 0, 0, 0])  # expecting 4 children and parents but might expand later
        parentList.append([0, 0, 0, 0])
        clearedChildList.append([0, 0, 0, 0])

    for element in range(len(elementList)):
        parentNode = elementList[element][0]
        childNode = elementList[element][1]
        i = 0
        while childList[parentNode][i] != 0:
            i += 1
            assert i < 4, 'More than 4 children detected'
        childList[parentNode][i] = childNode
        clearedChildList[parentNode][i] = childNode
        i = 0
        while parentList[childNode][i] != 0:
            i += 1
            assert i < 4, 'More than 4 parents detected'
        parentList[childNode][i] = parentNode

    # Identify start nodes, end nodes and junctions
    junctionCheck = [0] * (totalNodes + 2)
    startNodeCheck = [0] * (totalNodes + 2)
    endNodeCheck = [0] * (totalNodes + 2)

    for i in range(len(childList)):
        if childList[i][0] == 0:
            endNodeCheck[i] = 1
        if childList[i][1] > 0:
            junctionCheck[i] = 1
        if parentList[i][0] == 0:
            startNodeCheck[i] = 1
        if parentList[i][1] > 0:
            junctionCheck[i] = 1

    # Find points in a branch
    newNodeNumberList = [0] * (totalNodes + 2)
    reducedElementList = []
    reducedElementGroupsList = []
    newNodeCount = 0

    for element in range(len(elementList)):
        parentNode = elementList[element][0]
        if clearedChildList[parentNode][0] == 0:  # No child / child already removed
            continue
        else:
            childNode = elementList[element][1]
            childAtEndOfBranch = (junctionCheck[childNode] == 1 or endNodeCheck[childNode] == 1)
            if childAtEndOfBranch:
                # Store parent and child node and connectivity
                # Check for new numbering for nodes
                parentNewNodeNumber, newNodeNumberList, newNodeCount = getNewNodeNumber(parentNode, newNodeNumberList,
                                                                                        newNodeCount)
                childNewNodeNumber, newNodeNumberList, newNodeCount = getNewNodeNumber(childNode, newNodeNumberList,
                                                                                       newNodeCount)
                reducedElementList.append([parentNewNodeNumber, childNewNodeNumber])
                reducedElementGroupsList.append(elementGroupsList[element])
            else:  # child is not the end of branch
                nx = []
                branchNodes = []
                nx.append([float(xList[parentNode][c]) for c in range(3)])
                nx.append([float(xList[childNode][c]) for c in range(3)])
                branchNodes.append(parentNode)
                branchNodes.append(childNode)
                count = 0
                while not childAtEndOfBranch:
                    count += 1
                    assert count < 10000, 'Trapped in while loop'
                    childNode = childList[childNode][0]
                    childAtEndOfBranch = (junctionCheck[childNode] == 1 or endNodeCheck[
                        childNode] == 1 or childNode == parentNode)
                    nx.append([float(xList[childNode][c]) for c in range(3)])
                    branchNodes.append(childNode)

                # Null nodes inside a branch
                for i in range(1, len(branchNodes) - 1):
                    nodeInsideBranch = branchNodes[i]
                    clearedChildList[nodeInsideBranch][0] = 0

                # Down sample to target length between points within branch
                cumulativeLength = 0
                cumulativeLengthList = [0]
                for i in range(len(nx) - 1):
                    cumulativeLength += math.sqrt((nx[i][0] - nx[i + 1][0]) * (nx[i][0] - nx[i + 1][0]) +
                                                  (nx[i][1] - nx[i + 1][1]) * (nx[i][1] - nx[i + 1][1]) +
                                                  (nx[i][2] - nx[i + 1][2]) * (nx[i][2] - nx[i + 1][2]))
                    cumulativeLengthList.append(cumulativeLength)

                reducedElementCount = math.ceil(cumulativeLength / float(targetLength))
                if reducedElementCount > 0:
                    parentNewNodeNumber, newNodeNumberList, newNodeCount = getNewNodeNumber(parentNode,
                                                                                            newNodeNumberList,
                                                                                            newNodeCount)
                    for n in range(reducedElementCount):
                        distance = cumulativeLength / reducedElementCount * n
                        diff = [abs(cumulativeLengthList[c] - distance) for c in range(len(cumulativeLengthList))]
                        localNodeToRetain = diff.index(min(diff))
                        GlobalNodeToRetain = branchNodes[localNodeToRetain]
                        childNewNodeNumber, newNodeNumberList, newNodeCount = getNewNodeNumber(GlobalNodeToRetain,
                                                                                               newNodeNumberList,
                                                                                               newNodeCount)
                        reducedElementList.append([parentNewNodeNumber, childNewNodeNumber])
                        reducedElementGroupsList.append(elementGroupsList[element])
                        parentNode = GlobalNodeToRetain
                        parentNewNodeNumber, newNodeNumberList, newNodeCount = getNewNodeNumber(parentNode,
                                                                                                newNodeNumberList,
                                                                                                newNodeCount)
                    childNode = branchNodes[-1]
                    childNewNodeNumber, newNodeNumberList, newNodeCount = getNewNodeNumber(childNode, newNodeNumberList,
                                                                                           newNodeCount)
                    reducedElementList.append([parentNewNodeNumber, childNewNodeNumber])
                    reducedElementGroupsList.append(elementGroupsList[element])
                else:  # branch length is shorter than targetLength - keep parent and junction/end
                    parentNewNodeNumber, newNodeNumberList, newNodeCount = getNewNodeNumber(parentNode,
                                                                                            newNodeNumberList,
                                                                                            newNodeCount)
                    childNode = branchNodes[-1]
                    childNewNodeNumber, newNodeNumberList, newNodeCount = getNewNodeNumber(childNode, newNodeNumberList,
                                                                                           newNodeCount)
                    reducedElementList.append([parentNewNodeNumber, childNewNodeNumber])
                    reducedElementGroupsList.append(elementGroupsList[element])

    # print('Reduced number of nodes from', totalNodes - 1, 'to', newNodeCount)

    # Find old node numbering of retained nodes
    oldNumberOfReducedNodes = [0] * (newNodeCount + 1)
    for i in range(len(newNodeNumberList)):
        if newNodeNumberList[i] > 0:
            oldNumberOfReducedNodes[newNodeNumberList[i]] = i

    del tmpRegion

    # Create new region with downsampled nodes and elements
    fm = region.getFieldmodule()
    fm.beginChange()

    coordinates = find_or_create_field_coordinates(fm)
    nodes = fm.findNodesetByFieldDomainType(Field.DOMAIN_TYPE_NODES)
    nodetemplate = nodes.createNodetemplate()
    nodetemplate.defineField(coordinates)
    nodetemplate.setValueNumberOfVersions(coordinates, -1, Node.VALUE_LABEL_VALUE, 1)

    radius = findOrCreateFieldFiniteElement(fm, name='radius', components_count=1, type_coordinate=False)
    radiusNodetemplate = nodes.createNodetemplate()
    radiusNodetemplate.defineField(radius)

    rgb = findOrCreateFieldFiniteElement(fm, name='rgb', components_count=3, type_coordinate=False)
    rgbNodetemplate = nodes.createNodetemplate()
    rgbNodetemplate.defineField(rgb)

    cache = fm.createFieldcache()
    mesh1d = fm.findMeshByDimension(1)

    nodeIdentifier = 1
    elementIdentifier = 1

    linearLagrangeBasis = fm.createElementbasis(1, Elementbasis.FUNCTION_TYPE_LINEAR_LAGRANGE)
    eft = mesh1d.createElementfieldtemplate(linearLagrangeBasis)
    elementtemplate = mesh1d.createElementtemplate()
    elementtemplate.setElementShapeType(Element.SHAPE_TYPE_LINE)
    elementtemplate.defineField(coordinates, -1, eft)

    rgbElementtemplate = mesh1d.createElementtemplate()
    rgbElementtemplate.setElementShapeType(Element.SHAPE_TYPE_LINE)
    rgbElementtemplate.defineField(rgb, -1, eft)

    linearLagrangeBasis1D = fm.createElementbasis(1, Elementbasis.FUNCTION_TYPE_LINEAR_LAGRANGE)
    eft1 = mesh1d.createElementfieldtemplate(linearLagrangeBasis1D)
    radiusElementtemplate = mesh1d.createElementtemplate()
    radiusElementtemplate.setElementShapeType(Element.SHAPE_TYPE_LINE)
    radiusElementtemplate.defineField(radius, -1, eft1)

    for i in range(1, len(oldNumberOfReducedNodes)):
        node = nodes.createNode(nodeIdentifier, nodetemplate)
        cache.setNode(node)
        coordinates.setNodeParameters(cache, -1, Node.VALUE_LABEL_VALUE, 1, xList[oldNumberOfReducedNodes[i]])
        node.merge(radiusNodetemplate)
        node.merge(rgbNodetemplate)
        cache.setNode(node)
        radius.setNodeParameters(cache, -1, Node.VALUE_LABEL_VALUE, 1, radiusList[oldNumberOfReducedNodes[i]])
        rgb.setNodeParameters(cache, -1, Node.VALUE_LABEL_VALUE, 1, rgbList[oldNumberOfReducedNodes[i]])
        nodeIdentifier += 1

    allAnnotationGroups = []
    for fieldGroup in allGroups:
        fieldGroupName = fieldGroup.getName()
        if fieldGroupName != 'marker':
            allAnnotationGroups.append(AnnotationGroup(region, [fieldGroupName, "None"]))

    for i in range(len(reducedElementList)):
        nodeIdentifiers = [reducedElementList[i][0], reducedElementList[i][1]]
        element = mesh1d.createElement(elementIdentifier, elementtemplate)
        element.setNodesByIdentifier(eft, nodeIdentifiers)
        element.merge(radiusElementtemplate)
        element.merge(rgbElementtemplate)
        element.setNodesByIdentifier(eft1, nodeIdentifiers)
        element.setNodesByIdentifier(eft, nodeIdentifiers)
        for fieldGroupName in reducedElementGroupsList[i]:
            annotationGroup = findAnnotationGroupByName(allAnnotationGroups, fieldGroupName)
            if annotationGroup:
                meshGroup = annotationGroup.getMeshGroup(mesh1d)
                meshGroup.addElement(element)
        elementIdentifier += 1

    fm.endChange()

    fileName = filename.split('.')[0]
    outputFileName = fileName + '_reduced.exf'

    region.writeFile(outputFileName)

    return outputFileName


def getNewNodeNumber(oldNodeNumber, newNodeNumberList, newNodeCount):
    """
    Check newNodeNumberList for new node numbering. If already assigned,
    return the assigned node numbering, else assign new number.
    :param oldNodeNumber: original node numbering
    :param newNodeNumberList: List that stores new node numbering
    :param newNodeCount: Count track for new node index
    : return: new node number, updated node number list and
    updated new node count
    """

    if newNodeNumberList[oldNodeNumber] == 0:
        newNodeCount += 1
        newNodeNumberList[oldNodeNumber] = newNodeCount
        newNodeNumber = newNodeCount
    else:
        newNodeNumber = newNodeNumberList[oldNodeNumber]

    return newNodeNumber, newNodeNumberList, newNodeCount

